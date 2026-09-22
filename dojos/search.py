import requests
from django.contrib.gis.geos import Point
from django.db.models import ExpressionWrapper, F, FloatField
from django.utils import timezone

from events.models import Event
from geo.functions import DistanceSphere
from geo.geocoding import geocode

from .models import Dojo

# Default search origin/label before a real search is submitted — matches
# the dojo-finder search bar's old pre-filled example location.
DEFAULT_SEARCH_ORIGIN = Point(3.7174, 51.0543, srid=4326)  # Ghent, Belgium
DEFAULT_SEARCH_LABEL = "Ghent, Belgium"


def resolve_search_origin(form):
    """Given a bound DojoSearchForm, return (origin, search_label,
    geocode_failed) following the priority rules: typed address > browser
    lat/lon > default (Ghent). Shared by the full dojo-finder page and the
    homepage's embedded widget.
    """
    origin, search_label, geocode_failed = DEFAULT_SEARCH_ORIGIN, DEFAULT_SEARCH_LABEL, False

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
    """Dojo queryset annotated with distance_km from `origin` and ordered
    nearest-first — or the plain unordered queryset if origin is None (a
    failed geocode)."""
    qs = Dojo.objects.all()
    if origin is not None:
        qs = qs.annotate(
            distance_km=ExpressionWrapper(
                DistanceSphere(F("location"), origin) / 1000.0,
                output_field=FloatField(),
            )
        ).order_by(F("distance_km").asc(nulls_last=True))
    return qs


def attach_next_events(dojos):
    """Annotate each dojo in this (already-sliced) list with .next_event —
    one extra query total, instead of one per dojo."""
    upcoming = Event.objects.filter(
        dojo_id__in=[dojo.id for dojo in dojos], start_time__gte=timezone.now()
    ).order_by("start_time")
    next_event_by_dojo_id = {}
    for event in upcoming:
        next_event_by_dojo_id.setdefault(event.dojo_id, event)
    for dojo in dojos:
        dojo.next_event = next_event_by_dojo_id.get(dojo.id)
    return dojos
