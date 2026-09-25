from django.db.models import Q

from accounts.models import User

from ..base import USER, SegmentAttribute, SegmentChoice, choice_q


class AccountTypeAttribute(SegmentAttribute):
    key = "account_type"
    label = "Account type"
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
    label = "Has children on the site"
    value_type = "boolean"
    scope = USER

    def choices(self):
        return [SegmentChoice(True, "Yes"), SegmentChoice(False, "No")]

    def build_q(self, operator, value):
        if operator != "is":
            raise ValueError(f"Unsupported operator: {operator}")
        return Q(guardianships__isnull=not value)
