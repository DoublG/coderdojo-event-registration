from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse

from content import cache as content_cache
from content.models import Promotion
from core.profiling import profile
from dojos.forms import DojoSearchForm
from dojos.search import attach_next_events, dojos_by_distance, resolve_search_origin
from dojos.views import WIDGET_RESULTS_LIMIT
from events.search import WIDGET_PAGE_SIZE, upcoming_available_events


@profile()
def home(request):
    # Site-wide content that's the same for every visitor (pathways, the
    # organisation's team, FAQs, testimonials, promotions, sponsors) comes
    # from content.cache: cached, cleared whenever a row changes. The whole
    # page isn't cached: it carries per-request parts (the nav, the CSP
    # nonce, the dojo finder's origin).
    pathways = content_cache.pathways()
    # The organisation's own team — the homepage isn't tied to one dojo, so
    # "Meet the team" lists content.OrganisationTeamMember (display only,
    # each with a position, e.g. "Member of the board").
    team = content_cache.organisation_team()
    # A different quote on every load, picked from the cached few.
    testimonial = content_cache.random_testimonial()
    faqs = content_cache.global_faqs()

    # Initial state for the "Find a dojo near you" widget (dojos app) — its
    # own searches happen via htmx against dojos.views.dojo_finder_widget,
    # this is just what renders before anyone has searched.
    dojo_widget_form = DojoSearchForm()
    origin, dojo_widget_search_label, dojo_widget_geocode_failed = resolve_search_origin(
        dojo_widget_form, request.user
    )
    dojos = attach_next_events(list(dojos_by_distance(origin)[:WIDGET_RESULTS_LIMIT]))

    # Initial batch for the "Upcoming sessions" carousel (events app) —
    # further batches are lazy-loaded over htmx as it's scrolled, against
    # events.views.upcoming_sessions_widget.
    events_page = Paginator(upcoming_available_events(), WIDGET_PAGE_SIZE).get_page(1)
    events_next_page_url = None
    if events_page.has_next():
        events_next_page_url = f"{reverse('upcoming_sessions_widget')}?page={events_page.next_page_number()}"

    return render(
        request,
        "core/home.html",
        {
            "pathways": pathways,
            "team": team,
            "testimonial": testimonial,
            "faqs": faqs,
            "form": dojo_widget_form,
            "dojos": dojos,
            "search_label": dojo_widget_search_label,
            "geocode_failed": dojo_widget_geocode_failed,
            "events": events_page.object_list,
            "events_next_page_url": events_next_page_url,
            # Featured events (content.Promotion, DATA_MODEL.md §12), cached
            # until the next one starts or ends.
            "hero_promotions": content_cache.promotions_showing(Promotion.HOMEPAGE_HERO),
            "sponsors": content_cache.public_sponsors(),
        },
    )


def contact(request):
    """How to reach CoderDojo Belgium; dojo questions go to the dojo itself."""
    return render(request, "core/contact.html")


def code_of_conduct(request):
    """How everyone at a dojo (ninjas, parents, mentors, champions) behaves,
    and where to go with a concern."""
    return render(request, "core/code_of_conduct.html")
