import requests
from django.contrib.gis.db.models import PointField
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, ExpressionWrapper, F, FloatField, Q, QuerySet
from django.db.models.functions import Coalesce
from django.utils import timezone

from geo.functions import DistanceSphere
from geo.geocoding import geocode
from monitoring import recorder

from .models import Event

WIDGET_PAGE_SIZE = 10

# Backs both the homepage's and the account page's "upcoming sessions"/
# "awards" style lazy-loaded carousels — every page of either one comes
# from this same cached, pre-evaluated list, sliced in Python instead of
# re-querying per page. Saving or deleting a dojo, an event, a registration
# or a promotion clears it (events/signals.py, content.Promotion), so a
# change shows at once; the short TTL is only a safety net for writes that
# skip save(), like QuerySet.update().
CACHE_KEY = "events:upcoming_available"
CACHE_TIMEOUT = 60
CACHE_LIMIT = 200  # bound the cached list's size regardless of how far out events are scheduled


# The events list's first page without filters (events.views.event_list),
# cleared by the same signals.
EVENT_LIST_FIRST_PAGE_KEY = "events:list:first-page"
EVENT_LIST_CACHE_TIMEOUT = 60


# The events list's place filter: sessions within this distance of the
# place typed, measured from the session's own location, else its dojo's.
NEAR_RADIUS_KM = 20


def where_held() -> Coalesce:
    """A session's position: its own `location` when it has one (held
    somewhere else than the dojo), otherwise its dojo's."""
    return Coalesce(F("location"), F("dojo__location"), output_field=PointField(srid=4326))


def filter_by_place(events: "QuerySet[Event]", place: str) -> "QuerySet[Event]":
    """The events list's Location filter. The place is geocoded
    (geo.geocoding.geocode: the cache, the municipalities, then Nominatim):
    sessions held within NEAR_RADIUS_KM of it (where_held), annotated with
    `distance_km`. When it can't be placed (no match, or the geocoder is
    unavailable) it falls back to the text: the dojo's address or
    municipality, or the session's venue."""
    try:
        coords = geocode(place)
    except requests.RequestException:
        coords = None
    if coords is None:
        return events.filter(
            Q(dojo__address__icontains=place)
            | Q(dojo__municipality__name__icontains=place)
            | Q(venue_name__icontains=place)
        )
    lat, lon = coords
    origin = Point(lon, lat, srid=4326)
    return events.annotate(
        distance_km=ExpressionWrapper(DistanceSphere(where_held(), origin) / 1000.0, output_field=FloatField())
    ).filter(distance_km__lte=NEAR_RADIUS_KM)


def clear_event_list_cache() -> None:
    """Forget the events list's cached first page (now and on commit)."""
    from core.caching import clear

    clear(EVENT_LIST_FIRST_PAGE_KEY)


def clear_upcoming_cache() -> None:
    """Forget the cached list: now, and again once the current transaction
    commits (see dojos.search.clear_default_search_cache)."""
    cache.delete(CACHE_KEY)
    transaction.on_commit(lambda: cache.delete(CACHE_KEY))


def upcoming_available_events() -> list[Event]:
    """Upcoming events that still have open spots (or take registrations on
    another website), soonest first — except the ones promoted with the
    `upcoming_first` placement (content.Promotion), which come first, in
    rank order, marked `is_promoted`.

    "Available" is computed in the database (confirmed registrations vs.
    places) rather than via Event.places_left, since that property runs a
    query per event and can't be used to filter/order a queryset.

    Returns a cached, evaluated list (see CACHE_KEY) rather than a lazy
    queryset — callers only ever paginate/slice this, never filter it
    further, so the eager list is a drop-in replacement.
    """
    cached = cache.get(CACHE_KEY)
    recorder.note_cache(CACHE_KEY, hit=cached is not None)
    if cached is not None:
        return cached

    from content.models import Promotion

    now = timezone.now()
    events = list(
        Event.objects.visible()
        .filter(start_time__gte=now, status=Event.OPEN)
        .annotate(confirmed_count=Count("registration", filter=Q(registration__waiting_list=False)))
        .filter(Q(places__gt=F("confirmed_count")) | ~Q(external_registration_url=""))
        .select_related("dojo")
        .order_by("start_time")[:CACHE_LIMIT]
    )
    promoted: dict[int, int] = {}
    for promotion in Promotion.objects.showing(Promotion.UPCOMING_FIRST, now=now):
        promoted.setdefault(promotion.event_id, len(promoted))
    for event in events:
        event.is_promoted = event.id in promoted
    # A stable sort: promoted events first (by rank), the rest keep date order.
    events.sort(key=lambda event: promoted.get(event.id, len(promoted)))
    cache.set(CACHE_KEY, events, CACHE_TIMEOUT)
    return events
