"""Who is active: volunteers whose dojo is running sessions, and children
who come to sessions. Both take the same window (N days back from today),
so "everyone active" means the same thing on both sides."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dojos.models import Dojo, DojoMembership
from events.models import Event, Registration

from ..base import NINJA, USER, SegmentAttribute


def _held_sessions(days):
    """Non-draft events that started in the last `days` days."""
    now = timezone.now()
    return Event.objects.exclude(status=Event.DRAFT).filter(start_time__gte=now - timedelta(days=days), start_time__lte=now)


class ActiveTeamMemberAttribute(SegmentAttribute):
    """An active champion or mentor membership at an active dojo that held a
    session in the last N days. The account's background check isn't
    considered: it decides admin access, not whether someone volunteers."""

    key = "active_team_member"
    label = _("Champion or mentor at a dojo with sessions in the last N days")
    value_type = "days"
    scope = USER

    def choices(self):
        return []

    def build_q(self, operator, value):
        if operator != "within_days":
            raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
        memberships = DojoMembership.objects.managers().filter(
            dojo__status=Dojo.ACTIVE, dojo_id__in=_held_sessions(value).values("dojo_id"),
        )
        return Q(pk__in=memberships.values("user_id"))


class AttendedWithinDaysAttribute(SegmentAttribute):
    """The child came to a session in the last N days: marked present, or,
    for a session where the dojo marked nobody at all, had a confirmed
    (not waitlisted) place. Otherwise dojos that don't take attendance
    would make every child look inactive."""

    key = "attended_within_days"
    label = _("Came to a session in the last N days")
    value_type = "days"
    scope = NINJA

    def choices(self):
        return []

    def build_q(self, operator, value):
        if operator != "within_days":
            raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
        sessions = _held_sessions(value)
        unmarked = sessions.exclude(registration__attended__isnull=False)
        came = Registration.objects.filter(event__in=sessions.values("pk")).filter(
            Q(attended=True) | Q(waiting_list=False, attended__isnull=True, event__in=unmarked.values("pk"))
        )
        return Q(pk__in=came.values("ninja_id"))
