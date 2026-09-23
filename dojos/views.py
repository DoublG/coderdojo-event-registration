from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from content.models import FAQ

from .forms import DojoSearchForm
from .models import Dojo, Mentor
from .search import attach_next_events, dojos_by_distance, resolve_search_origin

RESULTS_PER_PAGE = 20
WIDGET_RESULTS_LIMIT = 5


def dojo_list(request):
    form = DojoSearchForm(request.GET)
    origin, search_label, geocode_failed = resolve_search_origin(form)
    dojos_qs = dojos_by_distance(origin)

    paginator = Paginator(dojos_qs, RESULTS_PER_PAGE)
    page = paginator.get_page(request.GET.get("page"))
    dojos = attach_next_events(list(page.object_list))

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


def dojo_finder_widget(request):
    """The compact "Find a dojo near you" widget embedded on the homepage
    (core/templates/core/home.html). Always returns just the meta line +
    result list fragment — this view has no full-page mode of its own, it's
    only ever reached via the widget's initial render or its htmx search."""
    form = DojoSearchForm(request.GET)
    origin, search_label, geocode_failed = resolve_search_origin(form)
    dojos = attach_next_events(list(dojos_by_distance(origin)[:WIDGET_RESULTS_LIMIT]))

    return render(request, "dojos/partials/_dojo_finder_widget_results.html", {
        "dojos": dojos,
        "search_label": search_label,
        "geocode_failed": geocode_failed,
    })


def dojo_detail(request, dojo_id):
    dojo = get_object_or_404(Dojo, id=dojo_id)
    next_event = dojo.event_set.filter(start_time__gte=timezone.now()).order_by("start_time").first()
    faqs = FAQ.objects.for_dojo(dojo)
    mentors = dojo.mentors.lead_coach_first()
    return render(request, "dojos/dojo_detail.html", {
        "dojo": dojo, "next_event": next_event, "faqs": faqs, "mentors": mentors,
    })


def dojo_team(request, dojo_id):
    dojo = get_object_or_404(Dojo, id=dojo_id)
    return render(request, "dojos/dojo_team.html", {"dojo": dojo, "mentors": dojo.mentors.lead_coach_first()})


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


def team_member_detail(request, mentor_id):
    """A detail page of their own is for the global team only — not a
    specific role, but Mentor.dojo being blank (see its help_text: "left
    blank for board members, who work across dojos"). A dojo's own
    mentors (lead coach, champion, ninja, volunteer) are shown inline on
    dojo_team.html instead, whatever their role."""
    mentor = get_object_or_404(Mentor, id=mentor_id, dojo__isnull=True)
    focus_areas = [area.strip() for area in mentor.focus_areas.split(",") if area.strip()]
    return render(request, "dojos/team_member_detail.html", {"mentor": mentor, "focus_areas": focus_areas})
