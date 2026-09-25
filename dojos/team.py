"""Changes to a dojo's team and lifecycle (DATA_MODEL.md §10). Views call
these rather than editing DojoMembership / Dojo.status directly, so the
rules live in one place:

- joining: an approved mentor asks to join (`requested`) and an active
  champion/mentor accepts or declines; or a champion/mentor adds them
  directly. Rejoining reuses the same (dormant) row.
- youth mentors: a ninja account promoted by a champion/mentor of the dojo.
- leaving / removing: the membership goes `dormant`, never deleted, so past
  events' teams keep their history. The champion can't leave; they transfer
  the champion role to an active mentor first (the old champion becomes a
  mentor).
- lifecycle: draft → active ⇄ dormant → archived → draft. Going dormant or
  archived needs no active events and auto-declines pending join requests.

Every rule violation raises TeamError with a message fit to show the user.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from events.models import Event
from notifications.services import notify

from .access import is_approved_mentor
from .models import Dojo, DojoMembership
from .search import DEFAULT_SEARCH_CACHE_KEY

# How long an active dojo can go without events before its team and the
# board are nudged to plan a session or mark it dormant.
DORMANCY_NUDGE_AFTER = timedelta(days=182)


class TeamError(Exception):
    pass


def _team_url(dojo):
    return reverse("dojo_team_manage", kwargs={"dojo_id": dojo.id})


def notify_managers(dojo, text, url="", exclude=None, params=None):
    """One notification per active champion/mentor of `dojo`, each in its
    recipient's language (see notifications.services.notify)."""
    for membership in dojo.memberships.managers().select_related("user"):
        if exclude is not None and membership.user_id == exclude.pk:
            continue
        notify(membership.user, text, url=url, dojo=dojo, params=params)


def _activate(membership, by=None):
    membership.status = DojoMembership.ACTIVE
    membership.joined_at = timezone.now()
    membership.left_at = None
    if by is not None:
        membership.decided_by = by


# --- joining ---------------------------------------------------------------

def request_to_join(dojo, user):
    if not is_approved_mentor(user):
        raise TeamError(_("Only approved mentors can ask to join a dojo's team."))
    if not dojo.is_public:
        raise TeamError(_("This dojo isn't accepting join requests right now."))
    membership = DojoMembership.objects.filter(dojo=dojo, user=user).first()
    if membership is not None and membership.status != DojoMembership.DORMANT:
        raise TeamError(_("You're already on this team, or your request is pending."))
    if membership is None:
        membership = DojoMembership(dojo=dojo, user=user, role=DojoMembership.MENTOR)
    membership.role = DojoMembership.MENTOR
    membership.status = DojoMembership.REQUESTED
    membership.requested_by = user
    membership.decided_by = None
    membership.save()
    notify_managers(dojo, gettext_lazy("%(name)s asked to join the %(dojo)s team."), url=_team_url(dojo),
                    params={"name": user.team_name, "dojo": dojo.name})
    return membership


def accept_request(membership, by):
    if membership.status != DojoMembership.REQUESTED:
        raise TeamError(_("That request has already been handled."))
    _activate(membership, by=by)
    membership.save()
    notify(membership.user, gettext_lazy("You're now on the %(dojo)s team."), dojo=None, params={"dojo": membership.dojo.name})
    return membership


def decline_request(membership, by, reason="declined"):
    """A declined request goes back to `dormant` if the person was on the
    team before (keeping their history), otherwise it's removed."""
    if membership.status != DojoMembership.REQUESTED:
        raise TeamError(_("That request has already been handled."))
    dojo = membership.dojo
    if membership.joined_at:
        membership.status = DojoMembership.DORMANT
        membership.decided_by = by
        membership.save()
    else:
        membership.delete()
    text = (
        gettext_lazy("Your request to join %(dojo)s was declined.")
        if reason == "declined"
        else gettext_lazy("Your request to join %(dojo)s was closed: the dojo is no longer active.")
    )
    notify(membership.user, text, params={"dojo": dojo.name})


def add_mentor(dojo, user, by):
    if not is_approved_mentor(user):
        raise TeamError(_("Only approved mentors can be added to a dojo's team."))
    membership = DojoMembership.objects.filter(dojo=dojo, user=user).first()
    if membership is not None and membership.status == DojoMembership.ACTIVE:
        raise TeamError(_("%(name)s is already on this team.") % {"name": user.team_name})
    if membership is None:
        membership = DojoMembership(dojo=dojo, user=user, requested_by=by)
    membership.role = DojoMembership.MENTOR
    _activate(membership, by=by)
    membership.save()
    notify(user, gettext_lazy("You've been added to the %(dojo)s team."), params={"dojo": dojo.name})
    return membership


def promote_youth_mentor(dojo, ninja_user, by_membership):
    if not ninja_user.is_ninja:
        raise TeamError(_("Only a ninja's own account can be promoted to youth mentor."))
    if not ninja_user.is_active:
        raise TeamError(_("%(name)s's login is switched off; their guardian can switch it back on.") % {"name": ninja_user.team_name})
    membership = DojoMembership.objects.filter(dojo=dojo, user=ninja_user).first()
    if membership is not None and membership.status == DojoMembership.ACTIVE:
        raise TeamError(_("%(name)s is already on this team.") % {"name": ninja_user.team_name})
    if membership is None:
        membership = DojoMembership(dojo=dojo, user=ninja_user)
    membership.role = DojoMembership.YOUTH_MENTOR
    membership.promoted_by = by_membership
    membership.requested_by = by_membership.user
    _activate(membership, by=by_membership.user)
    membership.save()
    # The family is informed, not asked (DATA_MODEL.md §18).
    from mailing.automated import youth_mentor_promoted_mail

    youth_mentor_promoted_mail(membership)
    return membership


# --- leaving ----------------------------------------------------------------

def _make_dormant(membership):
    membership.status = DojoMembership.DORMANT
    membership.left_at = timezone.now()
    membership.save(update_fields=["status", "left_at"])


def remove_member(membership):
    if membership.role == DojoMembership.CHAMPION:
        raise TeamError(_("The champion can't be removed; transfer the champion role first."))
    if membership.status != DojoMembership.ACTIVE:
        raise TeamError(_("Only active team members can be removed."))
    _make_dormant(membership)


def leave(membership):
    if membership.role == DojoMembership.CHAMPION:
        raise TeamError(_("As champion you can't leave; transfer the champion role to a mentor first."))
    _make_dormant(membership)


@transaction.atomic
def transfer_champion(dojo, from_membership, to_membership):
    if from_membership.role != DojoMembership.CHAMPION or from_membership.dojo_id != dojo.id:
        raise TeamError(_("Only the champion can hand over the champion role."))
    if (
        to_membership.dojo_id != dojo.id
        or to_membership.role != DojoMembership.MENTOR
        or to_membership.status != DojoMembership.ACTIVE
        or not to_membership.user.background_check_valid
    ):
        raise TeamError(_("The champion role can only go to an active mentor of this dojo with a valid background check."))
    from_membership.role = DojoMembership.MENTOR
    from_membership.save(update_fields=["role"])
    to_membership.role = DojoMembership.CHAMPION
    to_membership.save(update_fields=["role"])
    notify(to_membership.user, gettext_lazy("You're now the champion of %(dojo)s."), url=_team_url(dojo), dojo=dojo,
           params={"dojo": dojo.name})


# --- dojo lifecycle ------------------------------------------------------------

LIFECYCLE_ACTIONS = {
    # action: (allowed source statuses, target status)
    "launch": ({Dojo.DRAFT}, Dojo.ACTIVE),
    "go_dormant": ({Dojo.ACTIVE}, Dojo.DORMANT),
    "restart": ({Dojo.DORMANT}, Dojo.ACTIVE),
    "archive": ({Dojo.ACTIVE, Dojo.DORMANT}, Dojo.ARCHIVED),
    "reopen": ({Dojo.ARCHIVED}, Dojo.DRAFT),
}


def active_events(dojo):
    """Upcoming events still being prepared or open for sign-ups."""
    return dojo.event_set.filter(start_time__gte=timezone.now(), status__in=[Event.DRAFT, Event.OPEN])


def change_status(dojo, action):
    if action not in LIFECYCLE_ACTIONS:
        raise TeamError(_("Unknown action."))
    sources, target = LIFECYCLE_ACTIONS[action]
    if dojo.status not in sources:
        raise TeamError(_("That change isn't possible from the dojo's current status."))
    if target in (Dojo.DORMANT, Dojo.ARCHIVED) and active_events(dojo).exists():
        raise TeamError(
            _("This dojo still has upcoming events that are in draft or open for sign-ups. Close or finish those first.")
        )
    with transaction.atomic():
        dojo.status = target
        dojo.save(update_fields=["status"])
        # The dojo finder caches its default (unfiltered) result list.
        cache.delete(DEFAULT_SEARCH_CACHE_KEY)
        if target in (Dojo.DORMANT, Dojo.ARCHIVED):
            for membership in dojo.memberships.filter(status=DojoMembership.REQUESTED).select_related("user", "dojo"):
                decline_request(membership, by=None, reason="dojo_inactive")
    return dojo


def needs_dormancy_nudge(dojo):
    """An active dojo whose last event was over half a year ago and that has
    nothing coming up — shown as a banner on its dashboard until someone
    plans a session or marks it dormant (DATA_MODEL.md §10, decision 5).
    A dojo that has never held an event isn't nudged."""
    if dojo.status != Dojo.ACTIVE or dojo.is_organisation:
        return False
    now = timezone.now()
    if dojo.event_set.filter(start_time__gte=now).exists():
        return False
    last = dojo.event_set.filter(start_time__lt=now).order_by("-start_time").values_list("start_time", flat=True).first()
    return last is not None and now - last > DORMANCY_NUDGE_AFTER
