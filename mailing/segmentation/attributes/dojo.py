"""Attributes about a family's link with one dojo (DATA_MODEL.md §25), the
building blocks of the audiences a dojo's team can mail
(mailing.dojo_audiences). The account-level ones select a family without
using the children's details beyond that link (like the automated "new
sessions" mail), so no child-data consent is needed for them.

`in_builder = False` keeps an attribute out of the organisation's segment
builder, which has no fields for its kind of value."""

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from accounts.models import Guardianship
from dojos.models import Dojo
from events.models import Event, Registration

from ...dojo_families import active_since, ninjas_of
from ..base import NINJA, USER, SegmentAttribute, SegmentChoice


def _dojo_choices():
    return [SegmentChoice(d.pk, d.name) for d in Dojo.objects.exclude(status=Dojo.DRAFT).order_by("name")]


def _ids(operator, value):
    if operator == "equals":
        return [value]
    if operator in ("in", "not_in"):
        return list(value)
    raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})


def _guardians_of(ninjas):
    return Q(pk__in=Guardianship.objects.filter(ninja__in=ninjas).values("guardian_id"))


def _children_of_dojos(ids):
    since = active_since()
    q = Q(pk__in=[])
    for dojo_id in ids:
        q |= Q(pk__in=ninjas_of(dojo_id, since).values("pk"))
    return q


class ChildOfDojoAttribute(SegmentAttribute):
    """The child belongs to the dojo: it's their home dojo, or they came to
    one of its sessions in the last MAILING_DOJO_NEWS_ACTIVE_DAYS days."""

    key = "ninja_of_dojo"
    label = _("Child goes to dojo")
    value_type = "choice"
    scope = NINJA

    def choices(self):
        return _dojo_choices()

    def build_q(self, operator, value):
        matched = _children_of_dojos(_ids(operator, value))
        return ~matched if operator == "not_in" else matched


class DojoFamilyAttribute(SegmentAttribute):
    """A guardian of a child who goes to the dojo (ChildOfDojoAttribute): the
    families a dojo's news goes to (mailing.dojo_families)."""

    key = "dojo_family"
    label = _("Family of dojo")
    value_type = "choice"
    scope = USER

    def choices(self):
        return _dojo_choices()

    def build_q(self, operator, value):
        from accounts.models import Ninja

        matched = _guardians_of(Ninja.objects.filter(_children_of_dojos(_ids(operator, value))))
        return ~matched if operator == "not_in" else matched


class _FamilyRegisteredAttribute(SegmentAttribute):
    """A guardian of a child with a place for the session."""

    value_type = "choice"
    scope = USER
    waiting_list = False

    def choices(self):
        return [
            SegmentChoice(event.pk, str(event))
            for event in Event.objects.exclude(status=Event.DRAFT).order_by("-start_time")
        ]

    def build_q(self, operator, value):
        registrations = Registration.objects.filter(event_id__in=_ids(operator, value), waiting_list=self.waiting_list)
        matched = _guardians_of(registrations.values("ninja_id"))
        return ~matched if operator == "not_in" else matched


class FamilyBookedAttribute(_FamilyRegisteredAttribute):
    key = "family_booked_for_event"
    label = _("Family has a place for event")


class FamilyWaitlistedAttribute(_FamilyRegisteredAttribute):
    key = "family_waitlisted_for_event"
    label = _("Family is on the waiting list for event")
    waiting_list = True


class FamilyVisitedDojoAttribute(SegmentAttribute):
    """A guardian of a child who came to one of the dojo's sessions in the
    last N days (marked present). Value: {"dojo": id, "days": n}."""

    key = "family_visited_dojo"
    label = _("A child came to the dojo recently")
    value_type = "dojo_days"
    scope = USER
    operators = ["within_days"]
    in_builder = False

    def choices(self):
        return []

    def validate(self, operator, value):
        if (
            operator != "within_days"
            or not isinstance(value, dict)
            or not isinstance(value.get("days"), int)
            or isinstance(value.get("days"), bool)
            or value["days"] <= 0
            or not Dojo.objects.filter(pk=value.get("dojo")).exists()
        ):
            raise ValueError(_("“%(label)s” needs a dojo and a number of days.") % {"label": self.label})

    def build_q(self, operator, value):
        from datetime import timedelta

        from django.utils import timezone

        since = timezone.now() - timedelta(days=value["days"])
        came = Registration.objects.filter(
            event__dojo_id=value["dojo"],
            attended=True,
            event__start_time__gte=since,
            event__start_time__lte=timezone.now(),
        )
        return _guardians_of(came.values("ninja_id"))

    def describe(self, operator, value):
        dojo = Dojo.objects.filter(pk=value.get("dojo")).values_list("name", flat=True).first() or _("a dojo")
        return _("A child came to %(dojo)s in the last %(days)s days") % {"dojo": dojo, "days": value.get("days")}
