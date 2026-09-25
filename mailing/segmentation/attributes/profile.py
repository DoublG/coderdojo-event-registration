"""Tier 1 attributes (DATA_MODEL.md §11): who a child is and what they've
done, read straight from the site's own data (no snapshot needed)."""

from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import Guardianship
from dojos.models import Dojo, DojoMembership
from events.models import Badge, Belt, NinjaBadge, NinjaBelt, Registration, RegistrationCancellation
from pathways.models import Pathway

from ..base import NINJA, USER, SegmentAttribute, SegmentChoice, choice_q
from .event import EventAttribute

NO_BELT = 0


def _years_ago(years, today):
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # 29 February in a year without it
        return today.replace(year=today.year - years, day=28)


class NinjaAgeAttribute(SegmentAttribute):
    key = "ninja_age"
    label = _("Child's age")
    value_type = "number"
    scope = NINJA
    unit = _(" years")

    def choices(self):
        return []

    def build_q(self, operator, value):
        today = timezone.localdate()
        years = int(value)
        if operator == "gte":  # at least N: born on or before N years ago
            return Q(date_of_birth__lte=_years_ago(years, today))
        if operator == "lte":  # at most N: born after N+1 years ago
            return Q(date_of_birth__gt=_years_ago(years + 1, today))
        raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})


class HomeDojoAttribute(SegmentAttribute):
    key = "ninja_home_dojo"
    label = _("Child's home dojo")
    value_type = "choice"
    scope = NINJA

    def choices(self):
        return [SegmentChoice(d.pk, d.name) for d in Dojo.objects.exclude(status=Dojo.DRAFT).order_by("name")]

    def build_q(self, operator, value):
        return choice_q("home_dojo_id", operator, value)


class CurrentBeltAttribute(SegmentAttribute):
    """The child's current belt (the highest in their belt history)."""

    key = "current_belt"
    label = _("Child's current belt")
    value_type = "choice"
    scope = NINJA

    def choices(self):
        return [SegmentChoice(NO_BELT, _("No belt yet"))] + [SegmentChoice(b.level, b.localized("name")) for b in Belt.objects.order_by("level")]

    def build_q(self, operator, value):
        levels = [value] if operator == "equals" else list(value)
        highest = NinjaBelt.objects.values("ninja_id").annotate(top=Max("belt__level"))
        matched = Q(pk__in=highest.filter(top__in=[lv for lv in levels if lv != NO_BELT]).values("ninja_id"))
        if NO_BELT in levels:
            matched |= ~Q(pk__in=NinjaBelt.objects.values("ninja_id"))
        return ~matched if operator == "not_in" else matched


class HasBadgeAttribute(SegmentAttribute):
    key = "has_badge"
    label = _("Child has earned the badge")
    value_type = "choice"
    scope = NINJA

    def choices(self):
        return [SegmentChoice(b.pk, b.localized("name")) for b in Badge.objects.order_by("name")]

    def build_q(self, operator, value):
        ids = [value] if operator == "equals" else value
        matched = Q(pk__in=NinjaBadge.objects.filter(badge_id__in=ids, earned_date__isnull=False).values("ninja_id"))
        return ~matched if operator == "not_in" else matched


class PathwayAttribute(SegmentAttribute):
    """Worked on the pathway at a session (Registration.pathways)."""

    key = "pathway"
    label = _("Child worked on the pathway")
    value_type = "choice"
    scope = NINJA

    def choices(self):
        return [SegmentChoice(p.pk, p.localized("name")) for p in Pathway.objects.order_by("name")]

    def build_q(self, operator, value):
        ids = [value] if operator == "equals" else value
        matched = Q(pk__in=Registration.objects.filter(pathways__in=ids).values("ninja_id"))
        return ~matched if operator == "not_in" else matched


class WaitlistedForEventAttribute(EventAttribute):
    """On the waiting list for the event, e.g. to announce an extra session."""

    key = "waitlisted_for_event"
    label = _("On the waiting list for event")
    registrations = Registration.objects.filter(waiting_list=True)


class CancellationsAttribute(SegmentAttribute):
    key = "cancellations"
    label = _("Cancelled places (last 90 days)")
    value_type = "number"
    scope = NINJA

    def choices(self):
        return []

    def build_q(self, operator, value):
        since = timezone.now() - timedelta(days=90)
        counts = (RegistrationCancellation.objects.filter(cancelled_at__gte=since)
                  .values("ninja_id").annotate(n=Count("id")))
        if operator == "gte":
            return Q(pk__in=counts.filter(n__gte=value).values("ninja_id")) if value > 0 else Q()
        if operator == "lte":
            return ~Q(pk__in=counts.filter(n__gt=value).values("ninja_id"))
        raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})


ROLE_CHOICES = [
    ("guardian", _("Parent (has children on the site)")),
    ("mentor", _("Mentor (active)")),
    ("champion", _("Champion (active)")),
    ("organisation", _("Organisation role")),
]


class AccountRoleAttribute(SegmentAttribute):
    """What the account is on the site; one account can be several."""

    key = "account_role"
    label = _("Account's role")
    value_type = "choice"
    scope = USER

    def choices(self):
        return [SegmentChoice(value, label) for value, label in ROLE_CHOICES]

    def _role_q(self, role):
        if role == "guardian":
            return Q(pk__in=Guardianship.objects.values("guardian_id"))
        if role in ("mentor", "champion"):
            return Q(pk__in=DojoMembership.objects.filter(role=role, status=DojoMembership.ACTIVE).values("user_id"))
        return Q(organisation_roles__isnull=False)

    def build_q(self, operator, value):
        roles = [value] if operator == "equals" else value
        matched = Q(pk__in=[])
        for role in roles:
            matched |= self._role_q(role)
        return ~matched if operator == "not_in" else matched


class JoinedAttribute(SegmentAttribute):
    key = "joined_within_days"
    label = _("Account created in the last N days")
    value_type = "days"
    scope = USER

    def choices(self):
        return []

    def build_q(self, operator, value):
        if operator != "within_days":
            raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
        return Q(date_joined__gte=timezone.now() - timedelta(days=value))


