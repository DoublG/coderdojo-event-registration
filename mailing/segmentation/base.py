from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

USER = "user"
NINJA = "ninja"

# The operators each value type supports. A rule's operator is validated
# against its attribute's type when the rule is saved (SegmentRule.clean).
OPERATOR_LABELS = {
    "equals": _("is"),
    "in": _("is one of"),
    "not_in": _("is none of"),
    "is": _("is"),
    "within": _("within"),
    "within_days": _("in the last"),
    "gte": _("at least"),
    "lte": _("at most"),
}

OPERATORS = {
    "choice": ["equals", "in", "not_in"],
    "boolean": ["is"],
    "distance": ["within"],
    "days": ["within_days"],
    "number": ["gte", "lte"],
}


@dataclass(frozen=True)
class SegmentChoice:
    value: Any
    label: str


class SegmentAttribute(ABC):
    """One thing a segment rule can test.

    `scope` is what the returned Q filters: accounts.User (USER) or
    accounts.Ninja (NINJA). The resolver wraps every rule in its own
    subquery, so build_q can follow to-many relations freely."""

    key: str
    label: str
    value_type: str
    scope: str

    @abstractmethod
    def choices(self) -> list[SegmentChoice]:
        raise NotImplementedError

    @abstractmethod
    def build_q(
        self,
        operator: str,
        value: Any,
    ) -> Q:
        raise NotImplementedError

    @property
    def operators(self) -> list[str]:
        return OPERATORS[self.value_type]

    def validate(self, operator: str, value: Any) -> None:
        """Raise ValueError with a readable message for a rule that can't work."""
        if operator not in self.operators:
            raise ValueError(_("“%(label)s” supports %(join)s, not “%(operator)s”.") % {"label": self.label, "join": ', '.join(self.operators), "operator": operator})
        if self.value_type == "days":
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(_("“%(label)s” needs a whole number of days, e.g. 365.") % {"label": self.label})
            return
        if self.value_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ValueError(_("“%(label)s” needs a number, 0 or more.") % {"label": self.label})
            return
        if operator in ("in", "not_in"):
            if not isinstance(value, list) or not value:
                raise ValueError(_("“%(operator)s” needs a non-empty list of values.") % {"operator": operator})
            values = value
        else:
            values = [value]
        allowed = {choice.value for choice in self.choices()}
        unknown = [v for v in values if v not in allowed]
        if unknown:
            raise ValueError(_("Unknown value(s) for “%(label)s”: %(unknown)s.") % {"label": self.label, "unknown": unknown})


    # --- the segment builder (mailing.manage) -------------------------------

    def describe(self, operator: str, value: Any) -> str:
        """The rule as a readable phrase, e.g. "Child's gender is one of Girl, Prefer not to say"."""
        op = OPERATOR_LABELS.get(operator, operator)
        if self.value_type == "days":
            # The label says "... N days" in every language; N becomes the value.
            return re.sub(r"\bN\b", str(value), str(self.label))
        if self.value_type == "boolean":
            return f"{self.label}: {_('yes') if value else _('no')}"
        if self.value_type == "number":
            return f"{self.label} {op} {value:g}{getattr(self, 'unit', '')}"
        labels = {str(c.value): c.label for c in self.choices()}
        values = value if isinstance(value, list) else [value]
        return f"{self.label} {op} {', '.join(str(labels.get(str(v), v)) for v in values)}"

    def value_from_form(self, operator: str, data) -> Any:
        """The rule's JSON value from the builder's form fields (`data` is a
        QueryDict): choices come back as their real (typed) values."""
        by_text = {str(c.value): c.value for c in self.choices()}
        if self.value_type == "choice":
            if operator in ("in", "not_in"):
                return [by_text.get(v, v) for v in data.getlist("value")]
            return by_text.get(data.get("value", ""), data.get("value", ""))
        if self.value_type == "boolean":
            return data.get("value") == "true"
        if self.value_type in ("days", "number"):
            try:
                number = float(data.get("value", ""))
            except ValueError:
                return None
            return int(number) if number.is_integer() else number
        return data.get("value")


def number_q(field: str, operator: str, value: Any) -> Q:
    """The gte/lte Q on one numeric field, shared by number attributes."""
    if operator in ("gte", "lte"):
        return Q(**{f"{field}__{operator}": value})
    raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})


def choice_q(field: str, operator: str, value: Any) -> Q:
    """The equals/in/not_in Q on one field, shared by choice attributes."""
    if operator == "equals":
        return Q(**{field: value})
    if operator == "in":
        return Q(**{f"{field}__in": value})
    if operator == "not_in":
        return ~Q(**{f"{field}__in": value})
    raise ValueError(_("Unsupported operator: %(operator)s") % {"operator": operator})
