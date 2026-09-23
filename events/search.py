from django.core.cache import cache
from django.db.models import Count, F, Q
from django.utils import timezone

from .models import Event

WIDGET_PAGE_SIZE = 10

# Backs both the homepage's and the account page's "upcoming sessions"/
# "awards" style lazy-loaded carousels — every page of either one comes
# from this same cached, pre-evaluated list, sliced in Python instead of
# re-querying per page. Short TTL: the confirmed_count aggregate this
# filters on changes every time someone signs up for a session.
CACHE_KEY = "events:upcoming_available"
CACHE_TIMEOUT = 60
CACHE_LIMIT = 200  # bound the cached list's size regardless of how far out events are scheduled


def upcoming_available_events():
    """Upcoming events that still have open spots, soonest first.

    "Available" is computed in the database (confirmed registrations vs.
    places) rather than via Event.places_left, since that property runs a
    query per event and can't be used to filter/order a queryset.

    Returns a cached, evaluated list (see CACHE_KEY) rather than a lazy
    queryset — callers only ever paginate/slice this, never filter it
    further, so the eager list is a drop-in replacement.
    """
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    now = timezone.now()
    events = list(
        Event.objects.filter(start_time__gte=now, status=Event.OPEN)
        .annotate(confirmed_count=Count("registration", filter=Q(registration__waiting_list=False)))
        .filter(places__gt=F("confirmed_count"))
        .select_related("dojo")
        .order_by("start_time")[:CACHE_LIMIT]
    )
    cache.set(CACHE_KEY, events, CACHE_TIMEOUT)
    return events
