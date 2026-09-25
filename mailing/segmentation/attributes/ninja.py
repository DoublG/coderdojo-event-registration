from accounts.models import Ninja

from ..base import NINJA, SegmentAttribute, SegmentChoice, choice_q


class NinjaGenderAttribute(SegmentAttribute):
    key = "ninja_gender"
    label = "Child's gender"
    value_type = "choice"
    scope = NINJA

    def choices(self):
        return [SegmentChoice(value, label) for value, label in Ninja.GENDER_CHOICES]

    def build_q(self, operator, value):
        return choice_q("gender", operator, value)
