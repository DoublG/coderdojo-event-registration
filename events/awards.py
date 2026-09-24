"""Badges and belts: the rules for awarding them. Views and the attendance
flow call these; nothing else creates NinjaBelt rows (seeders aside).

- award_belt: a dojo's active champion or mentor awards a ninja the next
  belt(s) up. Belts are an append-only history, so a belt at or below the
  ninja's current level is refused, never overwritten.
- sync_milestones: recomputes a ninja's milestone badges (sessions
  attended) after attendance changes. A reached milestone that grants a
  belt awards it, as the membership that marked the attendance.
"""

from django.db import transaction
from django.utils import timezone

from .models import Badge, NinjaBadge, NinjaBelt, Registration


class BeltError(Exception):
    """A belt can't be awarded; the message is shown to the user."""


def _check_can_award(membership):
    # Imported here: dojos.access imports dojos.models, which the events
    # models reference by string only — keep the import graph one-way.
    from dojos.access import AWARD_BELTS, ROLE_CAPABILITIES
    from dojos.models import DojoMembership

    if (
        membership is None
        or membership.status != DojoMembership.ACTIVE
        or AWARD_BELTS not in ROLE_CAPABILITIES.get(membership.role, ())
        or not membership.user.background_check_valid
    ):
        raise BeltError("Only a dojo's active champion or mentors can award belts.")


def award_belt(ninja, belt, membership, note="", awarded_on=None):
    """Append `belt` to `ninja`'s belt history, awarded by `membership` (an
    active champion/mentor membership). The ninja must have a registration
    at one of that dojo's sessions, and the belt must be above their
    current one."""
    _check_can_award(membership)
    if not Registration.objects.filter(ninja=ninja, event__dojo_id=membership.dojo_id).exists():
        raise BeltError(f"{ninja.name} hasn't been to a session at {membership.dojo.name}.")
    current = ninja.current_belt
    if current and belt.level <= current.level:
        raise BeltError(f"{ninja.name} already has the {current.name} (or higher).")
    return NinjaBelt.objects.create(
        ninja=ninja, belt=belt, awarded_on=awarded_on or timezone.localdate(),
        awarded_by=membership.user, awarded_as_membership=membership, awarded_as_role=membership.role,
        note=note.strip(),
    )


@transaction.atomic
def sync_milestones(ninja, membership=None):
    """Bring `ninja`'s milestone badges in line with the sessions they've
    attended: every milestone reached is earned (and stays earned if
    attendance is later unmarked), and the next one up shows progress.
    Reaching one that `grants_belt` awards that belt as `membership`, if
    given and allowed to; otherwise the badge is still earned."""
    attended = Registration.objects.filter(ninja=ninja, attended=True).count()
    today = timezone.localdate()
    existing = {nb.badge_id: nb for nb in ninja.badges.filter(badge__kind=Badge.MILESTONE)}

    for badge in Badge.objects.filter(kind=Badge.MILESTONE).select_related("grants_belt").order_by("threshold"):
        ninja_badge = existing.get(badge.id)
        if ninja_badge and ninja_badge.earned_date:
            continue
        if attended >= badge.threshold:
            ninja_badge = ninja_badge or NinjaBadge(ninja=ninja, badge=badge)
            ninja_badge.earned_date = today
            ninja_badge.progress_current = ninja_badge.progress_total = badge.threshold
            ninja_badge.save()
            if badge.grants_belt and membership is not None:
                try:
                    award_belt(ninja, badge.grants_belt, membership, note=f"Reached the {badge.name} milestone.")
                except BeltError:
                    pass  # already at that belt or higher, or not theirs to award
            continue
        # The next milestone up: show progress toward it, then stop.
        ninja_badge = ninja_badge or NinjaBadge(ninja=ninja, badge=badge)
        ninja_badge.progress_current, ninja_badge.progress_total = attended, badge.threshold
        ninja_badge.save()
        break
