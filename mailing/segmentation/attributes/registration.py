from events.models import Registration

from .event import EventAttribute


class AttendedEventAttribute(EventAttribute):
    """The child was marked present at the event (Registration.attended)."""

    key = "attended_event"
    label = "Attended event"
    registrations = Registration.objects.filter(attended=True)
