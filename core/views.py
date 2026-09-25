from django.core.cache import cache
from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse

from content.models import FAQ, OrganisationTeamMember, Promotion, Testimonial
from dojos.forms import DojoSearchForm
from dojos.search import attach_next_events, dojos_by_distance, resolve_search_origin
from dojos.views import WIDGET_RESULTS_LIMIT
from events.search import WIDGET_PAGE_SIZE, upcoming_available_events
from pathways.models import Pathway

# Site-wide content that barely ever changes and is identical for every
# visitor (unlike, say, the dojo-finder widget's results, which vary by
# origin) — cached here rather than via cache_page on the whole view, since
# the page also renders per-user chrome (see core/templates/core/menu.html:
# login state, account links) that must never be cached.
HOME_CONTENT_CACHE_TIMEOUT = 300


def home(request):
    pathways = cache.get_or_set("core:home:pathways", lambda: list(Pathway.objects.all()), HOME_CONTENT_CACHE_TIMEOUT)

    # The organisation's own team — the homepage isn't tied to one dojo, so
    # "Meet the team" lists content.OrganisationTeamMember (display only,
    # each with a position, e.g. "Member of the board").
    team = cache.get_or_set(
        "core:home:team", lambda: list(OrganisationTeamMember.objects.filter(is_public=True)), HOME_CONTENT_CACHE_TIMEOUT
    )

    # A different quote on every load — order_by("?") is fine at this size
    # (a handful of site-wide testimonials, dojo=None). Deliberately *not*
    # cached: that's the whole point of this query.
    testimonial = Testimonial.objects.filter(dojo=None).order_by("?").first()

    faqs = cache.get_or_set("core:home:faqs", lambda: list(FAQ.objects.global_faqs()), HOME_CONTENT_CACHE_TIMEOUT)

    # Initial state for the "Find a dojo near you" widget (dojos app) — its
    # own searches happen via htmx against dojos.views.dojo_finder_widget,
    # this is just what renders before anyone has searched.
    dojo_widget_form = DojoSearchForm()
    origin, dojo_widget_search_label, dojo_widget_geocode_failed = resolve_search_origin(dojo_widget_form, request.user)
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
        "team": team,
        "testimonial": testimonial,
        "faqs": faqs,
        "form": dojo_widget_form,
        "dojos": dojos,
        "search_label": dojo_widget_search_label,
        "geocode_failed": dojo_widget_geocode_failed,
        "events": events_page.object_list,
        "events_next_page_url": events_next_page_url,
        # Featured events (content.Promotion, DATA_MODEL.md §12). Not cached:
        # a promotion starts and ends on its own schedule.
        "hero_promotions": Promotion.objects.showing(Promotion.HOMEPAGE_HERO),
        "finder_promotions": Promotion.objects.showing(Promotion.DOJO_FINDER_BANNER),
    })
