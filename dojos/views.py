from django.contrib.gis.geos import Point
from django.db.models import ExpressionWrapper, F, FloatField
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template import loader
from django.utils import timezone

from events.models import Event
from geo.functions import DistanceSphere

from .models import Dojo, Mentor

# Matches the dojo-finder search bar's pre-filled example location, so the
# page shows a real "nearest first" list before a real postcode search is
# wired up (the search bar itself isn't hooked up to a view yet).
DEFAULT_SEARCH_ORIGIN = Point(3.7174, 51.0543, srid=4326)  # Ghent, Belgium


def dojo_list(request):
    dojos = list(
        Dojo.objects.annotate(
            distance_km=ExpressionWrapper(
                DistanceSphere(F("location"), DEFAULT_SEARCH_ORIGIN) / 1000.0,
                output_field=FloatField(),
            )
        ).order_by(F("distance_km").asc(nulls_last=True))
    )

    # One extra query for everyone's next event, instead of one per dojo:
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

    template = loader.get_template("dojos/dojo_list.html")
    return HttpResponse(template.render({"dojos": dojos}, request))


def dojo_detail(request, dojo_id):
    dojo = get_object_or_404(Dojo, id=dojo_id)
    next_event = dojo.event_set.filter(start_time__gte=timezone.now()).order_by("start_time").first()
    template = loader.get_template("dojos/dojo_detail.html")
    return HttpResponse(template.render({"dojo": dojo, "next_event": next_event}, request))


def dojo_team(request, dojo_id):
    dojo = get_object_or_404(Dojo, id=dojo_id)
    template = loader.get_template("dojos/dojo_team.html")
    return HttpResponse(template.render({"dojo": dojo, "mentors": dojo.mentors.all()}, request))


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

    template = loader.get_template("dojos/dojo_dashboard.html")
    return HttpResponse(template.render(
        {
            "dojo": dojo,
            "session": session,
            "registrations": registrations,
            "present_count": present_count,
        },
        request,
    ))


def mentor_profile(request, mentor_id):
    mentor = get_object_or_404(Mentor, id=mentor_id)
    focus_areas = [area.strip() for area in mentor.focus_areas.split(",") if area.strip()]
    template = loader.get_template("dojos/mentor_profile.html")
    return HttpResponse(template.render({"mentor": mentor, "focus_areas": focus_areas}, request))
