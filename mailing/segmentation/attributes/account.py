from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from accounts.models import User

from ..base import USER, SegmentAttribute, SegmentChoice, choice_q


class AccountTypeAttribute(SegmentAttribute):
    key = "account_type"
    label = _("Account type")
    value_type = "choice"
    scope = USER

    def choices(self):
        return [SegmentChoice(value, label) for value, label in User.ACCOUNT_TYPE_CHOICES]

    def build_q(self, operator, value):
        return choice_q("account_type", operator, value)


class HasChildrenAttribute(SegmentAttribute):
    """The account is a guardian of at least one ninja (accounts.Guardianship):
    a family rather than, say, a mentor who happens to live nearby."""

    key = "has_children"
    label = _("Has children on the site")
    value_type = "boolean"
    scope = USER

    def choices(self):
        return [SegmentChoice(True, _("Yes")), SegmentChoice(False, _("No"))]

    def build_q(self, operator, value):
        if operator != "is":
            raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
        return Q(guardianships__isnull=not value)
