from django.db.models import Q

from events.models import Event, Registration

from ..base import NINJA, SegmentAttribute, SegmentChoice


class EventAttribute(SegmentAttribute):
    """The child has a registration (confirmed or waitlisted) for the event."""

    key = "event"
    label = "Registered for event"
    value_type = "choice"
    scope = NINJA
    registrations = Registration.objects.all()

    def choices(self):
        return [
            SegmentChoice(event.pk, str(event))
            for event in Event.objects.exclude(status=Event.DRAFT).order_by("-start_time")
        ]

    def build_q(self, operator, value):
        event_ids = [value] if operator == "equals" else value
        matched = Q(pk__in=self.registrations.filter(event_id__in=event_ids).values("ninja_id"))
        if operator in ("equals", "in"):
            return matched
        if operator == "not_in":
            return ~matched
        raise ValueError(f"Unsupported operator: {operator}")
