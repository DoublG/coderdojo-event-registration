from django.db.models import QuerySet

from ..base import SegmentAttribute, SegmentChoice


class RegistrationStatusAttribute(SegmentAttribute):
    key = "registration_status"
    label = "Registration status"
    value_type = "choice"

    def choices(self) -> list[SegmentChoice]:
        return [
            SegmentChoice("pending", "Pending"),
            SegmentChoice("confirmed", "Confirmed"),
            SegmentChoice("cancelled", "Cancelled"),
            SegmentChoice("attended", "Attended"),
        ]

    def apply(
        self,
        queryset: QuerySet,
        operator: str,
        value,
    ) -> QuerySet:

        if operator == "equals":
            return queryset.filter(
                registrations__status=value,
            )

        if operator == "in":
            return queryset.filter(
                registrations__status__in=value,
            )

        raise ValueError(
            f"Unsupported operator: {operator}"
        )
