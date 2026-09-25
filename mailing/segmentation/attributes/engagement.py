"""Attributes on the engagement snapshot (events.NinjaEngagement, rebuilt
nightly by events.engagement): how a child comes to sessions, measured
against the sessions meant for them. The overall row (dojo empty) is
measured at the child's main dojo; StageAtDojoAttribute reads a dojo's own
row. Figures are as of the last nightly rebuild."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dojos.models import Dojo
from events.models import NinjaEngagement

from ..base import NINJA, SegmentAttribute, SegmentChoice, choice_q, number_q


def _overall(q):
    return Q(pk__in=NinjaEngagement.objects.filter(q, dojo__isnull=True).values("ninja_id"))


class _EngagementAttribute(SegmentAttribute):
    scope = NINJA
    field = ""

    def choices(self):
        return []

    def build_q(self, operator, value):
        return _overall(number_q(self.field, operator, value))


class EngagementStageAttribute(SegmentAttribute):
    key = "engagement_stage"
    label = _("How the child comes to sessions")
    value_type = "choice"
    scope = NINJA

    def choices(self):
        return [SegmentChoice(value, label) for value, label in NinjaEngagement.STAGE_CHOICES]

    def build_q(self, operator, value):
        return _overall(choice_q("stage", operator, value))


class StageAtDojoAttribute(SegmentAttribute):
    """The stage at one dojo, e.g. "at risk at CoderDojo Ghent".
    Value: {"dojo": id, "stages": [...]}."""

    key = "engagement_stage_at_dojo"
    label = _("How the child comes to one dojo")
    value_type = "dojo_stage"
    scope = NINJA
    operators = ["in"]

    def choices(self):
        return [SegmentChoice(value, label) for value, label in NinjaEngagement.STAGE_CHOICES]

    def dojo_choices(self):
        return [SegmentChoice(d.pk, d.name) for d in Dojo.objects.exclude(status=Dojo.DRAFT).order_by("name")]

    def validate(self, operator, value):
        if operator != "in":
            raise ValueError(_("“%(label)s” supports in, not “%(operator)s”.") % {"label": self.label, "operator": operator})
        stages = {c.value for c in self.choices()}
        if (not isinstance(value, dict) or value.get("dojo") not in {c.value for c in self.dojo_choices()}
                or not value.get("stages") or not set(value["stages"]) <= stages):
            raise ValueError(_("“%(label)s” needs a dojo and at least one stage.") % {"label": self.label})

    def build_q(self, operator, value):
        return Q(pk__in=NinjaEngagement.objects.filter(dojo_id=value["dojo"], stage__in=value["stages"])
                 .values("ninja_id"))

    def describe(self, operator, value):
        labels = {c.value: c.label for c in self.choices()}
        dojo = dict((c.value, c.label) for c in self.dojo_choices()).get(value.get("dojo"), _("a dojo"))
        return _("At %(dojo)s: %(stages)s") % {"dojo": dojo, "stages": ", ".join(str(labels.get(s, s)) for s in value.get("stages", []))}

    def value_from_form(self, operator, data):
        try:
            return {"dojo": int(data.get("dojo", "")), "stages": data.getlist("value")}
        except ValueError:
            return None


class AttendanceRateAttribute(_EngagementAttribute):
    key = "attendance_rate"
    label = _("Share of their sessions they came to (last 180 days, %)")
    value_type = "number"
    unit = _("%")

    def build_q(self, operator, value):
        return _overall(number_q("attendance_rate", operator, value / 100))


class SessionsAttendedAttribute(_EngagementAttribute):
    key = "sessions_attended"
    label = _("Sessions they came to in the last 180 days")
    value_type = "number"
    field = "attended_180d"


class MissedInARowAttribute(_EngagementAttribute):
    key = "missed_in_a_row"
    label = _("Sessions missed in a row")
    value_type = "number"
    field = "missed_in_a_row"


class NoShowsAttribute(_EngagementAttribute):
    key = "no_shows"
    label = _("Booked but didn't come (last 90 days)")
    value_type = "number"
    field = "no_shows_90d"


class DaysSinceLastVisitAttribute(_EngagementAttribute):
    key = "days_since_last_visit"
    label = _("Days since their last session")
    value_type = "number"
    unit = _(" days")

    def build_q(self, operator, value):
        # More days since the last visit = an earlier last visit.
        cutoff = timezone.localdate() - timedelta(days=int(value))
        lookup = "last_attended__lte" if operator == "gte" else "last_attended__gte"
        if operator not in ("gte", "lte"):
            raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
        return _overall(Q(**{lookup: cutoff}))


class HasUpcomingAttribute(SegmentAttribute):
    key = "has_upcoming_registration"
    label = _("Has a session booked")
    value_type = "boolean"
    scope = NINJA

    def choices(self):
        return [SegmentChoice(True, _("Yes")), SegmentChoice(False, _("No"))]

    def build_q(self, operator, value):
        if operator != "is":
            raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
        return _overall(Q(has_upcoming=bool(value)))


class MainDojoStatusAttribute(SegmentAttribute):
    """E.g. families whose dojo went dormant: "find another dojo near you"."""

    key = "main_dojo_status"
    label = _("Status of their main dojo")
    value_type = "choice"
    scope = NINJA

    def choices(self):
        return [SegmentChoice(value, label) for value, label in Dojo.STATUS_CHOICES]

    def build_q(self, operator, value):
        return _overall(choice_q("main_dojo__status", operator, value))
