from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse

from dojos.forms import DojoSearchForm
from dojos.search import attach_next_events, dojos_by_distance, resolve_search_origin
from dojos.views import WIDGET_RESULTS_LIMIT
from events.search import WIDGET_PAGE_SIZE, upcoming_available_events
from pathways.models import Pathway


def home(request):
    pathways = Pathway.objects.all()

    # Initial state for the "Find a dojo near you" widget (dojos app) — its
    # own searches happen via htmx against dojos.views.dojo_finder_widget,
    # this is just what renders before anyone has searched.
    dojo_widget_form = DojoSearchForm()
    origin, dojo_widget_search_label, dojo_widget_geocode_failed = resolve_search_origin(dojo_widget_form)
    dojos = attach_next_events(list(dojos_by_distance(origin)[:WIDGET_RESULTS_LIMIT]))

    # Initial batch for the "Upcoming sessions" carousel (events app) —
    # further batches are lazy-loaded over htmx as it's scrolled, against
    # events.views.upcoming_sessions_widget.
    events_page = Paginator(upcoming_available_events(), WIDGET_PAGE_SIZE).get_page(1)
    events_next_page_url = None
    if events_page.has_next():
        events_next_page_url = f"{reverse('upcoming_sessions_widget')}?page={events_page.next_page_number()}"

    return render(request, "core/home.html", {
        "pathways": pathways,
        "form": dojo_widget_form,
        "dojos": dojos,
        "search_label": dojo_widget_search_label,
        "geocode_failed": dojo_widget_geocode_failed,
        "events": events_page.object_list,
        "events_next_page_url": events_next_page_url,
    })
