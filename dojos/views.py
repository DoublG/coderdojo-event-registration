import requests
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from content.models import FAQ
from geo.geocoding import find_province, geocode
from notifications.models import Notification

from .forms import DojoProfileForm, DojoSearchForm
from .models import Dojo, Mentor
from .search import attach_next_events, dojos_by_distance, resolve_search_origin

RESULTS_PER_PAGE = 20
WIDGET_RESULTS_LIMIT = 5
NOTIFICATION_LIMIT = 10


def _get_owned_dojo(request, dojo_id):
    """A dojo owner's own admin pages (dashboard, manage): 404s rather than
    403s for a mismatch, so a guessed id doesn't even confirm another
    dojo's existence — same reasoning as accounts._get_own_guardian."""
    dojo = get_object_or_404(Dojo, id=dojo_id)
    if dojo.owner_id != request.user.pk:
        raise Http404
    return dojo


def _notification_context(user, dojo):
    """Shared by every admin view that renders dojos/templates/dojos/
    partials/_notification_bell.html on initial page load — the exact
    same query shape notifications.consumers.NotificationConsumer and
    mark_all_notifications_read below use for their own re-renders, kept
    in one place so "what counts as this dojo's notifications for this
    user" can't drift between the three."""
    notifications = Notification.objects.filter(recipient=user, dojo=dojo)[:NOTIFICATION_LIMIT]
    unread_count = Notification.objects.filter(recipient=user, dojo=dojo, read=False).count()
    return {"notifications": notifications, "unread_count": unread_count}


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


@login_required
def dojo_dashboard(request, dojo_id):
    dojo = _get_owned_dojo(request, dojo_id)
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
        "active": "attendance",
        **_notification_context(request.user, dojo),
    })


@login_required
def dojo_manage(request, dojo_id):
    """Lets a dojo owner edit everything shown on their dojo's public
    profile (dojo_detail.html) — see DojoProfileForm for the exact field
    list. Address changes are re-geocoded on save (same tolerant-failure
    pattern as dojos.search.resolve_search_origin: a failed/no-match
    geocode never blocks the save, it just leaves location/province as
    they were), and a successful geocode also refreshes province via
    geo.geocoding.find_province so distance search and the map link stay
    accurate without the owner ever touching either field directly."""
    dojo = _get_owned_dojo(request, dojo_id)
    saved = False
    geocode_failed = False

    if request.method == "POST":
        form = DojoProfileForm(request.POST, request.FILES, instance=dojo)
        if form.is_valid():
            address_changed = "address" in form.changed_data
            dojo = form.save(commit=False)

            if address_changed and dojo.address:
                try:
                    coords = geocode(dojo.address)
                except requests.RequestException:
                    coords = None
                if coords:
                    lat, lon = coords
                    dojo.location = Point(lon, lat, srid=4326)
                    dojo.province = find_province(dojo.location)
                else:
                    geocode_failed = True

            dojo.save()
            saved = True
    else:
        form = DojoProfileForm(instance=dojo)

    return render(request, "dojos/dojo_manage.html", {
        "dojo": dojo, "form": form, "saved": saved, "geocode_failed": geocode_failed, "active": "settings",
        **_notification_context(request.user, dojo),
    })


@login_required
def open_notification(request, dojo_id, notification_id):
    """What a notification item's link actually points at (see
    _notification_bell.html) — marks it read then sends the owner on to
    wherever it's actually about, matching the design system's own "clicking
    one should... typically navigate" guidance. A plain GET/redirect, not
    htmx: this is a real navigation, not an in-place update.

    recipient=request.user (on top of the usual dojo-ownership check) matters
    here specifically — read state is per-recipient, so one owner must not
    be able to mark a co-owner's copy of a dojo-level notification read."""
    dojo = _get_owned_dojo(request, dojo_id)
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user, dojo=dojo)
    if not notification.read:
        notification.read = True
        notification.save(update_fields=["read"])
    return redirect(notification.url or reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))


@login_required
def mark_all_notifications_read(request, dojo_id):
    """The bell panel's "Mark all as read" — htmx (hx-swap="none" on the
    form, see _notification_bell.html): the response's own hx-swap-oob="true"
    root is what actually places it, so no target/swap mode needs setting
    here beyond suppressing htmx's normal (non-oob) placement."""
    dojo = _get_owned_dojo(request, dojo_id)
    if request.method == "POST":
        Notification.objects.filter(recipient=request.user, dojo=dojo, read=False).update(read=True)
    return render(request, "dojos/partials/_notification_bell.html", {
        "dojo": dojo, **_notification_context(request.user, dojo),
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
