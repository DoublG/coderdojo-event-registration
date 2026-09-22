from django.db.models import Count, F, Q
from django.utils import timezone

from .models import Event

WIDGET_PAGE_SIZE = 10


def upcoming_available_events():
    """Upcoming events that still have open spots, soonest first.

    "Available" is computed in the database (confirmed registrations vs.
    places) rather than via Event.places_left, since that property runs a
    query per event and can't be used to filter/order a queryset.
    """
    now = timezone.now()
    return (
        Event.objects.filter(start_time__gte=now)
        .annotate(confirmed_count=Count("registration", filter=Q(registration__waiting_list=False)))
        .filter(places__gt=F("confirmed_count"))
        .select_related("dojo")
        .order_by("start_time")
    )
