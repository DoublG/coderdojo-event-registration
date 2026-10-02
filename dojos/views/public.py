"""The public pages: the dojo finder and its homepage widget, a dojo's page and
team, asking to join, and an organisation team member's page."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from content.cache import promotions_showing
from content.models import OrganisationTeamMember, Promotion

from .. import public_cache, team
from ..access import is_approved_mentor
from ..forms import DojoSearchForm
from ..models import Dojo, DojoMembership
from ..search import attach_next_events, dojos_by_distance, resolve_search_origin
from .common import RESULTS_PER_PAGE, WIDGET_RESULTS_LIMIT


def dojo_list(request):
    form = DojoSearchForm(request.GET)
    origin, search_label, geocode_failed = resolve_search_origin(form, request.user)
    language = form.cleaned_data.get("language") if form.is_valid() else None
    dojos_qs = dojos_by_distance(origin, language=language)

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
        "promotions": promotions_showing(Promotion.DOJO_FINDER_BANNER),
    }
    # Infinite scroll (htmx "revealed" trigger, see _dojo_result.html):
    # subsequent pages return just the new <li> fragment, not the full page.
    if request.headers.get("HX-Request") == "true":
        return render(request, "dojos/partials/_dojo_results_page.html", context)
    return render(request, "dojos/dojo_list.html", context)


def dojo_finder_widget(request):
    """The compact "Find a dojo near you" widget embedded on the homepage
    (pages/templates/pages/home.html). Always returns just the meta line +
    result list fragment — this view has no full-page mode of its own, it's
    only ever reached via the widget's initial render or its htmx search."""
    form = DojoSearchForm(request.GET)
    origin, search_label, geocode_failed = resolve_search_origin(form, request.user)
    dojos = attach_next_events(list(dojos_by_distance(origin)[:WIDGET_RESULTS_LIMIT]))

    return render(
        request,
        "dojos/partials/_dojo_finder_widget_results.html",
        {
            "dojos": dojos,
            "search_label": search_label,
            "geocode_failed": geocode_failed,
        },
    )


def _join_state(user, dojo):
    """For the public dojo page's "Join the team" box: "member" (already on
    the team), "requested" (waiting for an answer), "can_request" (an
    approved mentor who can ask), or None (nothing to show)."""
    if not user.is_authenticated:
        return None
    membership = dojo.memberships.filter(user=user).first()
    if membership is not None and membership.status == DojoMembership.ACTIVE:
        return "member"
    if membership is not None and membership.status == DojoMembership.REQUESTED:
        return "requested"
    return "can_request" if is_approved_mentor(user) else None


def dojo_detail(request, dojo_id):
    # The dojo, its FAQs, updates and team are cached per dojo
    # (dojos.public_cache); the next session's places and the join button
    # are worked out per request.
    page = public_cache.detail(dojo_id)
    dojo = page["dojo"]
    next_event = (
        dojo.event_set.visible()
        .filter(start_time__gte=timezone.now())
        .with_confirmed_count()
        .order_by("start_time")
        .first()
    )
    return render(
        request,
        "dojos/dojo_detail.html",
        {
            **page,
            "next_event": next_event,
            "join_state": _join_state(request.user, dojo),
        },
    )


def dojo_team(request, dojo_id):
    dojo = get_object_or_404(Dojo.objects.public(), id=dojo_id)
    return render(request, "dojos/dojo_team.html", {"dojo": dojo, "mentors": dojo.memberships.for_team_page()})


@login_required
def dojo_join_request(request, dojo_id):
    """An approved mentor asks to join a dojo's team (POST only); its
    champion/mentors accept or decline from their Team page."""
    dojo = get_object_or_404(Dojo.objects.public(), id=dojo_id)
    if request.method == "POST":
        try:
            team.request_to_join(dojo, request.user)
            messages.success(
                request, _("Your request to join %(dojo)s has been sent to its team.") % {"dojo": dojo.name}
            )
        except team.TeamError as error:
            messages.error(request, str(error))
    return redirect("dojo_detail", dojo_id=dojo.id)


def team_member_detail(request, member_id):
    """The organisation's team details page for one listed person
    (content.OrganisationTeamMember — display only, e.g. "Member of the
    board"). A dojo's own team is shown on dojo_team.html instead."""
    member = get_object_or_404(OrganisationTeamMember, id=member_id, is_public=True)
    return render(
        request,
        "dojos/team_member_detail.html",
        {
            "mentor": member,
            "focus_areas": member.focus_area_list,
        },
    )
