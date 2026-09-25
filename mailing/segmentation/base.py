from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from django.db.models import Q

USER = "user"
NINJA = "ninja"

# The operators each value type supports. A rule's operator is validated
# against its attribute's type when the rule is saved (SegmentRule.clean).
OPERATOR_LABELS = {
    "equals": "is",
    "in": "is one of",
    "not_in": "is none of",
    "is": "is",
    "within": "within",
    "within_days": "in the last",
}

OPERATORS = {
    "choice": ["equals", "in", "not_in"],
    "boolean": ["is"],
    "distance": ["within"],
    "days": ["within_days"],
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
            raise ValueError(f"“{self.label}” supports {', '.join(self.operators)}, not “{operator}”.")
        if self.value_type == "days":
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"“{self.label}” needs a whole number of days, e.g. 365.")
            return
        if operator in ("in", "not_in"):
            if not isinstance(value, list) or not value:
                raise ValueError(f"“{operator}” needs a non-empty list of values.")
            values = value
        else:
            values = [value]
        allowed = {choice.value for choice in self.choices()}
        unknown = [v for v in values if v not in allowed]
        if unknown:
            raise ValueError(f"Unknown value(s) for “{self.label}”: {unknown}.")


    # --- the segment builder (mailing.manage) -------------------------------

    def describe(self, operator: str, value: Any) -> str:
        """The rule as a readable phrase, e.g. "Child's gender is one of Girl, Prefer not to say"."""
        op = OPERATOR_LABELS.get(operator, operator)
        if self.value_type == "days":
            return f"{self.label.replace(' in the last N days', '')} {op} {value} days"
        if self.value_type == "boolean":
            return f"{self.label}: {'yes' if value else 'no'}"
        labels = {str(c.value): c.label for c in self.choices()}
        values = value if isinstance(value, list) else [value]
        return f"{self.label} {op} {', '.join(labels.get(str(v), str(v)) for v in values)}"

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
        if self.value_type == "days":
            try:
                return int(data.get("value", ""))
            except ValueError:
                return None
        return data.get("value")


def choice_q(field: str, operator: str, value: Any) -> Q:
    """The equals/in/not_in Q on one field, shared by choice attributes."""
    if operator == "equals":
        return Q(**{field: value})
    if operator == "in":
        return Q(**{f"{field}__in": value})
    if operator == "not_in":
        return ~Q(**{f"{field}__in": value})
    raise ValueError(f"Unsupported operator: {operator}")
