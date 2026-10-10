from typing import Any

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from accounts.models import Ninja

from ..base import NINJA, SegmentAttribute, SegmentChoice, choice_q


class NinjaGenderAttribute(SegmentAttribute):
    key = "ninja_gender"
    label = _("Child's gender")
    value_type = "choice"
    scope = NINJA

    def choices(self) -> list[SegmentChoice]:
        return [SegmentChoice(value, label) for value, label in Ninja.GENDER_CHOICES]

    def build_q(self, operator: str, value: Any) -> Q:
        return choice_q("gender", operator, value)
