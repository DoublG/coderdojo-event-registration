from django.db.models import QuerySet

from events.models import Event

from ..base import SegmentAttribute, SegmentChoice


from django.db.models import Q

from events.models import Event

from ..base import SegmentAttribute, SegmentChoice


class EventAttribute(SegmentAttribute):
    key = "event"
    label = "Registered for event"
    value_type = "choice"

    def choices(self):
        return [
            SegmentChoice(
                event.pk,
                event.name,
            )
            for event in Event.objects
            .filter(is_active=True)
            .order_by("name")
        ]

    def build_q(self, operator, value):
        if operator == "equals":
            return Q(
                registrations__event_id=value
            )

        if operator == "not_equals":
            return ~Q(
                registrations__event_id=value
            )

        if operator == "in":
            return Q(
                registrations__event_id__in=value
            )

        if operator == "not_in":
            return ~Q(
                registrations__event_id__in=value
            )

        raise ValueError(
            f"Unsupported operator: {operator}"
        )
