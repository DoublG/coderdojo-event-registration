"""Marking who came to a session: the children with a confirmed place
(`Registration.attended`) and the session's team (`TeamAttendance`), all
tri-state (None = not marked yet). Shared by the dojo team's attendance
list (dojos.views) and the attendance API (api.v1), so both follow the
same rules: every change is a save() (the audit log only sees saves), and
milestone badges follow a child's attendance (events.awards.sync_milestones).
"""

from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from accounts.models import Ninja

from .awards import sync_milestones
from .models import Event, Registration, TeamAttendance

if TYPE_CHECKING:
    from accounts.models import User
    from dojos.models import DojoMembership


def confirmed_registrations(event: Event) -> QuerySet[Registration]:
    """The children with a confirmed (not waitlisted) place, by name."""
    return (
        event.registration_set.filter(waiting_list=False)
        .select_related("ninja")
        .order_by("ninja__name", "ninja__family_name")
    )


def team_rows(event: Event) -> list[dict[str, Any]]:
    """One {membership, attended} per person on the session's team
    (`Event.team`), champion first; `attended` from TeamAttendance, None
    when not marked yet."""
    marks = dict(TeamAttendance.objects.filter(event=event).values_list("membership_id", "attended"))
    memberships = event.team.select_related("user", "dojo").order_by("role", "user__first_name")
    return [{"membership": m, "attended": marks.get(m.id)} for m in memberships]


def mark_child(
    registration: Registration, attended: bool | None, awarded_as: "DojoMembership | None" = None
) -> Registration:
    """Present (True), absent (False) or not marked (None) for one confirmed
    registration. A milestone that grants a belt awards it as `awarded_as`
    (a membership allowed to), else only the badge is earned."""
    if registration.attended != attended:
        registration.attended = attended
        registration.save(update_fields=["attended"])
    sync_milestones(registration.ninja, awarded_as)
    return registration


def mark_team_member(
    event: Event, membership: "DojoMembership", attended: bool | None, marked_by: "User"
) -> TeamAttendance:
    """Present, absent or not marked for one person on the session's team;
    `marked_by` is the account that marked it (a person, or an API client's
    technical account)."""
    record, _created = TeamAttendance.objects.update_or_create(
        event=event,
        membership=membership,
        defaults={"attended": attended, "marked_by": marked_by},
    )
    return record


def mark_all_present(event: Event, marked_by: "User", awarded_as: "DojoMembership | None" = None) -> None:
    """Every confirmed child and everyone on the team present."""
    confirmed = event.registration_set.filter(waiting_list=False)
    for registration in confirmed.exclude(attended=True):
        registration.attended = True
        registration.save(update_fields=["attended"])
    for ninja in Ninja.objects.filter(registration__in=confirmed):
        sync_milestones(ninja, awarded_as)
    for membership in event.team.all():
        mark_team_member(event, membership, True, marked_by)
