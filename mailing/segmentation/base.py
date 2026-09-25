from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from django.db.models import Q

from django.db.models import QuerySet


@dataclass(frozen=True)
class SegmentChoice:
    value: Any
    label: str


class SegmentAttribute(ABC):
    key: str
    label: str
    value_type: str

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
