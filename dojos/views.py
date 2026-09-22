import requests
from django.contrib.gis.geos import Point
from django.core.paginator import Paginator
from django.db.models import ExpressionWrapper, F, FloatField
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from events.models import Event
from geo.functions import DistanceSphere
from geo.geocoding import geocode

from .forms import DojoSearchForm
from .models import Dojo, Mentor

# Default search origin/label before a real search is submitted — matches
# the dojo-finder search bar's old pre-filled example location.
DEFAULT_SEARCH_ORIGIN = Point(3.7174, 51.0543, srid=4326)  # Ghent, Belgium
DEFAULT_SEARCH_LABEL = "Ghent, Belgium"

RESULTS_PER_PAGE = 20


def dojo_list(request):
    form = DojoSearchForm(request.GET)
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

    dojos_qs = Dojo.objects.all()
    if origin is not None:
        dojos_qs = dojos_qs.annotate(
            distance_km=ExpressionWrapper(
                DistanceSphere(F("location"), origin) / 1000.0,
                output_field=FloatField(),
            )
        ).order_by(F("distance_km").asc(nulls_last=True))

    paginator = Paginator(dojos_qs, RESULTS_PER_PAGE)
    page = paginator.get_page(request.GET.get("page"))
    dojos = list(page.object_list)

    # One extra query for this page's next events, instead of one per dojo:
    # take the events ordered by start_time and keep the first (soonest) one
    # seen per dojo.
    upcoming = Event.objects.filter(
        dojo_id__in=[dojo.id for dojo in dojos], start_time__gte=timezone.now()
    ).order_by("start_time")
    next_event_by_dojo_id = {}
    for event in upcoming:
        next_event_by_dojo_id.setdefault(event.dojo_id, event)
    for dojo in dojos:
        dojo.next_event = next_event_by_dojo_id.get(dojo.id)

    next_page_url = None
    if page.has_next():
        next_params = request.GET.copy()
        next_params["page"] = page.next_page_number()
        next_page_url = f"{request.path}?{next_params.urlencode()}"

    context = {
        "form": form,
        "dojos": dojos,
        "search_label": search_label,
        "geocode_failed": geocode_failed,
        "total_count": paginator.count,
        "next_page_url": next_page_url,
    }
    # Infinite scroll (htmx "revealed" trigger, see _dojo_result.html):
    # subsequent pages return just the new <li> fragment, not the full page.
    if request.headers.get("HX-Request") == "true":
        return render(request, "dojos/partials/_dojo_results_page.html", context)
    return render(request, "dojos/dojo_list.html", context)


def dojo_detail(request, dojo_id):
    dojo = get_object_or_404(Dojo, id=dojo_id)
    next_event = dojo.event_set.filter(start_time__gte=timezone.now()).order_by("start_time").first()
    return render(request, "dojos/dojo_detail.html", {"dojo": dojo, "next_event": next_event})


def dojo_team(request, dojo_id):
    dojo = get_object_or_404(Dojo, id=dojo_id)
    return render(request, "dojos/dojo_team.html", {"dojo": dojo, "mentors": dojo.mentors.all()})


def dojo_dashboard(request, dojo_id):
    dojo = get_object_or_404(Dojo, id=dojo_id)
    # The session whose attendance we're managing: the next upcoming one, or
    # else the most recent past one, so the page still shows something once
    # a dojo's calendar has run out.
    session = dojo.event_set.filter(start_time__gte=timezone.now()).order_by("start_time").first()
    if session is None:
        session = dojo.event_set.order_by("-start_time").first()

    registrations = []
    if session is not None:
        registrations = (
            session.registration_set.filter(waiting_list=False)
            .select_related("participant", "pathway")
            .order_by("participant__name")
        )
    present_count = sum(1 for r in registrations if r.attended)

    return render(request, "dojos/dojo_dashboard.html", {
        "dojo": dojo,
        "session": session,
        "registrations": registrations,
        "present_count": present_count,
    })


def mentor_profile(request, mentor_id):
    mentor = get_object_or_404(Mentor, id=mentor_id)
    focus_areas = [area.strip() for area in mentor.focus_areas.split(",") if area.strip()]
    return render(request, "dojos/mentor_profile.html", {"mentor": mentor, "focus_areas": focus_areas})
