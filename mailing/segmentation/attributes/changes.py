"""Tier 3 attributes (DATA_MODEL.md §11): change over time, for journeys
(mailing.journeys) and "time for something new" campaigns."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dojos.models import DojoMembership
from events.models import NinjaBelt, NinjaEngagement, NinjaEngagementChange

from ..base import NINJA, USER, SegmentAttribute, SegmentChoice


class StageChangedAttribute(SegmentAttribute):
    """The child's overall stage changed recently, e.g. from regular to at
    risk. Value: {"from": [...] (empty = any), "to": [...], "days": N}."""

    key = "stage_changed"
    label = _("How the child comes to sessions changed")
    value_type = "stage_change"
    scope = NINJA
    operators = ["within_days"]

    def choices(self):
        return [SegmentChoice(value, label) for value, label in NinjaEngagement.STAGE_CHOICES]

    def validate(self, operator, value):
        stages = {c.value for c in self.choices()}
        if (operator != "within_days" or not isinstance(value, dict) or not value.get("to")
                or not set(value["to"]) <= stages or not set(value.get("from") or []) <= stages
                or not isinstance(value.get("days"), int) or value["days"] <= 0):
            raise ValueError(_("“%(label)s” needs the new stage(s) and a number of days.") % {"label": self.label})

    def build_q(self, operator, value):
        changes = NinjaEngagementChange.objects.filter(
            to_stage__in=value["to"], changed_on__gte=timezone.localdate() - timedelta(days=value["days"]),
        )
        if value.get("from"):
            changes = changes.filter(from_stage__in=value["from"])
        return Q(pk__in=changes.values("ninja_id"))

    def describe(self, operator, value):
        labels = {c.value: c.label for c in self.choices()}
        names = lambda stages: str(_(" or ")).join(str(labels.get(s, s)) for s in stages)  # noqa: E731
        if value.get("from"):
            return _("Became %(to)s from %(from)s in the last %(days)s days") % {
                "to": names(value.get("to", [])), "from": names(value["from"]), "days": value.get("days"),
            }
        return _("Became %(to)s in the last %(days)s days") % {"to": names(value.get("to", [])), "days": value.get("days")}

    def value_from_form(self, operator, data):
        try:
            days = int(data.get("days", ""))
        except ValueError:
            days = None
        return {"from": data.getlist("from"), "to": data.getlist("value"), "days": days}


class NoNewBeltAttribute(SegmentAttribute):
    """No belt awarded in the last N days (or none at all): with "regular",
    children who might like a new pathway."""

    key = "no_new_belt_within_days"
    label = _("No new belt in the last N days")
    value_type = "days"
    scope = NINJA

    def choices(self):
        return []

    def build_q(self, operator, value):
        if operator != "within_days":
            raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
        recent = NinjaBelt.objects.filter(awarded_on__gte=timezone.localdate() - timedelta(days=value))
        return ~Q(pk__in=recent.values("ninja_id"))


class NotOnATeamAttribute(SegmentAttribute):
    """Not on any session's team (Event.team) in the last N days: with
    "Account's role: mentor", volunteers who've drifted away."""

    key = "not_on_team_within_days"
    label = _("Not on a session team in the last N days")
    value_type = "days"
    scope = USER

    def choices(self):
        return []

    def build_q(self, operator, value):
        if operator != "within_days":
            raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
        since = timezone.now() - timedelta(days=value)
        recent = DojoMembership.objects.filter(events__start_time__gte=since, events__start_time__lte=timezone.now())
        return ~Q(pk__in=recent.values("user_id"))
