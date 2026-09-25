import requests
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.db.models import ExpressionWrapper, F, FloatField
from django.utils import timezone

from events.models import Event
from geo.functions import DistanceSphere
from geo.geocoding import geocode
from geo.models import Municipality

from .models import Dojo

# Default search origin/label before a real search is submitted — matches
# the dojo-finder search bar's old pre-filled example location.
DEFAULT_SEARCH_ORIGIN = Point(3.7174, 51.0543, srid=4326)  # Ghent, Belgium
DEFAULT_SEARCH_LABEL = "Ghent, Belgium"

# Every homepage load and every bare (no search submitted) dojo_list visit
# resolves to this exact origin — by far the most common case, so it's the
# one worth caching. Short TTL: dojo data changes rarely, but this keeps a
# newly-added dojo from being invisible for long.
DEFAULT_SEARCH_CACHE_KEY = "dojos:by_distance:default_origin"
DEFAULT_SEARCH_CACHE_TIMEOUT = 60


def postal_code_origin(postal_code):
    """(Point, label) for a Belgian postcode: the average of its
    municipality centres (a postcode can cover several localities), or
    None for an unknown or empty postcode."""
    if not postal_code:
        return None
    municipalities = list(Municipality.objects.filter(postal_code=postal_code).order_by("id"))
    if not municipalities:
        return None
    lon = sum(m.center.x for m in municipalities) / len(municipalities)
    lat = sum(m.center.y for m in municipalities) / len(municipalities)
    return Point(lon, lat, srid=4326), f"{postal_code} {municipalities[0].name}"


def resolve_search_origin(form, user=None):
    """Given a bound DojoSearchForm, return (origin, search_label,
    geocode_failed) following the priority rules: typed address > browser
    lat/lon > the logged-in account's postcode (User.postal_code, optional)
    > default (Ghent). Shared by the full dojo-finder page and the
    homepage's embedded widget.
    """
    origin, search_label, geocode_failed = DEFAULT_SEARCH_ORIGIN, DEFAULT_SEARCH_LABEL, False
    if user is not None and user.is_authenticated and (home := postal_code_origin(user.postal_code)):
        # Not cached like the Ghent default (dojos_by_distance checks the
        # origin's identity), so one family's list never leaks to another.
        origin, search_label = home

    # A typed address always wins over lat/lon, even if both are present in
    # the request: the lat/lon hidden fields are re-rendered with their old
    # bound value on every reload (Django forms echo back submitted data),
    # so after "Use my location" they'd otherwise keep silently overriding
    # a brand-new address the user types afterwards.
    if form.is_valid() and form.cleaned_data["location"]:
        search_label = form.cleaned_data["location"]
        try:
            coords = geocode(search_label)
        except requests.RequestException:
            coords = None
        if coords:
            lat, lon = coords
            origin = Point(lon, lat, srid=4326)
        else:
            origin, geocode_failed = None, True
    elif form.is_valid() and form.cleaned_data["lat"] is not None and form.cleaned_data["lon"] is not None:
        # "Use my location": browser-supplied coordinates, no geocoding needed.
        origin = Point(form.cleaned_data["lon"], form.cleaned_data["lat"], srid=4326)
        search_label = "your location"

    return origin, search_label, geocode_failed


def dojos_by_distance(origin):
    """Dojo list annotated with distance_km from `origin` and ordered
    nearest-first — or the plain unordered queryset if origin is None (a
    failed geocode).

    Returns a plain (evaluated) list for the default origin, since that
    result is cached — see DEFAULT_SEARCH_CACHE_KEY. Otherwise returns the
    lazy queryset as before; caching every possible typed-in search would
    have an unbounded key space for little benefit.
    """
    is_default = origin is DEFAULT_SEARCH_ORIGIN
    if is_default:
        cached = cache.get(DEFAULT_SEARCH_CACHE_KEY)
        if cached is not None:
            return cached

    qs = Dojo.objects.public()
    if origin is not None:
        qs = qs.annotate(
            distance_km=ExpressionWrapper(
                DistanceSphere(F("location"), origin) / 1000.0,
                output_field=FloatField(),
            )
        ).order_by(F("distance_km").asc(nulls_last=True))

    if is_default:
        qs = list(qs)
        cache.set(DEFAULT_SEARCH_CACHE_KEY, qs, DEFAULT_SEARCH_CACHE_TIMEOUT)
    return qs


def attach_next_events(dojos):
    """Annotate each dojo in this (already-sliced) list with .next_event —
    one extra query total, instead of one per dojo."""
    upcoming = Event.objects.visible().filter(
        dojo_id__in=[dojo.id for dojo in dojos], start_time__gte=timezone.now()
    ).order_by("start_time")
    next_event_by_dojo_id = {}
    for event in upcoming:
        next_event_by_dojo_id.setdefault(event.dojo_id, event)
    for dojo in dojos:
        dojo.next_event = next_event_by_dojo_id.get(dojo.id)
    return dojos
