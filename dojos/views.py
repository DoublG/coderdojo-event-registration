import requests
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from content.models import FAQ
from events.forms import EventForm
from events.models import Event, Registration
from geo.geocoding import find_province, geocode
from notifications.models import Notification

from .access import EDIT_SETTINGS, MANAGE_EVENTS, TAKE_ATTENDANCE, accessible_dojos, require_dojo_access
from .forms import DojoProfileForm, DojoSearchForm
from .models import Dojo, Mentor
from .search import attach_next_events, dojos_by_distance, resolve_search_origin

RESULTS_PER_PAGE = 20
WIDGET_RESULTS_LIMIT = 5
NOTIFICATION_LIMIT = 10


def _admin_context(request, access):
    """What every page extending dojos/_admin_base.html needs besides its
    own content: the dojo, the viewer's role/capabilities (`dojo_access`,
    see dojos.access), the dojos they can switch between, and the
    notification bell."""
    return {
        "dojo": access.dojo,
        "dojo_access": access,
        "admin_dojos": accessible_dojos(request.user),
        **_notification_context(request.user, access.dojo),
    }


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
    next_event = dojo.event_set.visible().filter(start_time__gte=timezone.now()).order_by("start_time").first()
    faqs = FAQ.objects.for_dojo(dojo)
    mentors = dojo.mentors.lead_coach_first()
    return render(request, "dojos/dojo_detail.html", {
        "dojo": dojo, "next_event": next_event, "faqs": faqs, "mentors": mentors,
    })


def dojo_team(request, dojo_id):
    dojo = get_object_or_404(Dojo, id=dojo_id)
    return render(request, "dojos/dojo_team.html", {"dojo": dojo, "mentors": dojo.mentors.lead_coach_first()})


def _attendance_context(event):
    """What dojos/partials/_attendance.html needs for one event: its
    confirmed (not waitlisted) registrations, alphabetical, plus how many
    are already marked present. Shared by the dashboard, the per-event
    attendance page and the htmx endpoints that re-render parts of it."""
    registrations = list(
        event.registration_set.filter(waiting_list=False)
        .select_related("participant", "pathway")
        .order_by("participant__name")
    )
    return {
        "event": event,
        "registrations": registrations,
        "present_count": sum(1 for r in registrations if r.attended),
    }


@login_required
def dojo_dashboard(request, dojo_id):
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    # The session whose attendance we're managing: the next upcoming one, or
    # else the most recent past one, so the page still shows something once
    # a dojo's calendar has run out.
    session = dojo.event_set.filter(start_time__gte=timezone.now()).order_by("start_time").first()
    if session is None:
        session = dojo.event_set.order_by("-start_time").first()

    return render(request, "dojos/dojo_dashboard.html", {
        "session": session,
        **(_attendance_context(session) if session is not None else {}),
        "active": "attendance",
        **_admin_context(request, access),
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
    access = require_dojo_access(request, dojo_id, EDIT_SETTINGS)
    dojo = access.dojo
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
        "form": form, "saved": saved, "geocode_failed": geocode_failed, "active": "settings",
        **_admin_context(request, access),
    })


@login_required
def dojo_event_list(request, dojo_id):
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    events = dojo.event_set.order_by("-start_time")
    return render(request, "dojos/dojo_event_list.html", {
        "events": events, "active": "events",
        **_admin_context(request, access),
    })


@login_required
def dojo_event_create(request, dojo_id):
    """A new session always starts out Draft (Event.status' model default)
    — see EventForm's docstring for why status isn't a field on this form
    at all. The owner publishes it (draft -> open) from the events list
    or its detail page once it's ready, via dojo_event_set_status."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=Event(dojo=dojo), dojo=dojo)
        if form.is_valid():
            form.save()
            return redirect("dojo_event_list", dojo_id=dojo.id)
    else:
        form = EventForm(instance=Event(dojo=dojo), dojo=dojo)

    return render(request, "dojos/dojo_event_create.html", {
        "form": form, "active": "events",
        **_admin_context(request, access),
    })


@login_required
def dojo_event_detail(request, dojo_id, event_id):
    """Edit an existing event — same EventForm as dojo_event_create, just
    bound to an existing instance (EventForm.__init__ pre-fills event_date/
    start_time/end_time from it). Re-renders in place on success, same
    "no redirect, just show a saved banner" convention as dojo_manage,
    since this is an edit-in-place settings-style form, not a one-shot
    creation. Status is changed separately, via dojo_event_set_status —
    the status card at the top of the template posts there directly, so
    saving the form never touches status and vice versa."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    saved = False

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event, dojo=dojo)
        if form.is_valid():
            event = form.save()
            saved = True
    else:
        form = EventForm(instance=event, dojo=dojo)

    return render(request, "dojos/dojo_event_detail.html", {
        "event": event, "form": form, "saved": saved, "active": "events",
        **_admin_context(request, access),
    })


@login_required
def dojo_event_set_status(request, dojo_id, event_id):
    """Sets an event's status directly — any of draft/open/closed, from any
    other one. Not a one-way lifecycle: an owner can reopen a closed
    session, or pull a published one back to draft (hiding it from the
    public site again — existing registrations are kept, not cancelled).
    Posting an absolute target status (rather than a "next step" action)
    keeps a stale page or double-click harmless: it just re-applies the
    same status. An unknown status value is ignored.

    Redirects back to `next` (posted by whichever page linked here — the
    list or the detail page) when it's a safe same-site URL, else falls
    back to the events list."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(Event.STATUS_CHOICES) and new_status != event.status:
            event.status = new_status
            event.save(update_fields=["status"])

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("dojo_event_list", dojo_id=dojo.id)


ATTENDANCE_VALUES = {"present": True, "absent": False, "none": None}


@login_required
def dojo_event_attendance(request, dojo_id, event_id):
    """Take attendance for one specific session — reached from that event's
    detail page. Same list as the dashboard's (dojos/partials/_attendance.html),
    which only ever shows the next/most recent session."""
    access = require_dojo_access(request, dojo_id, TAKE_ATTENDANCE)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    return render(request, "dojos/dojo_event_attendance.html", {
        **_attendance_context(event),
        "active": "events",
        **_admin_context(request, access),
    })


@login_required
def dojo_event_attendance_mark(request, dojo_id, event_id, registration_id):
    """Set one confirmed registration's `attended` to present/absent/none
    (POST `attended`). An htmx request gets back just that row, plus the
    "N of M present" summary out-of-band; a plain form post (no JS)
    redirects back to the event's attendance page. Waitlisted registrations
    404 — only confirmed places are listed, so only those can be marked."""
    access = require_dojo_access(request, dojo_id, TAKE_ATTENDANCE)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    registration = get_object_or_404(
        Registration.objects.select_related("participant", "pathway"),
        id=registration_id, event=event, waiting_list=False,
    )

    if request.method == "POST" and request.POST.get("attended") in ATTENDANCE_VALUES:
        registration.attended = ATTENDANCE_VALUES[request.POST["attended"]]
        registration.save(update_fields=["attended"])

    if request.headers.get("HX-Request"):
        context = {"dojo": dojo, "dojo_access": access, **_attendance_context(event), "registration": registration}
        row = render_to_string("dojos/partials/_attendance_row.html", context, request=request)
        summary = render_to_string("dojos/partials/_attendance_summary.html", {**context, "oob": True}, request=request)
        return HttpResponse(row + summary)
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)


@login_required
def dojo_event_attendance_mark_all(request, dojo_id, event_id):
    """The "Mark all present" button — every confirmed registration for the event. An
    htmx request gets the whole re-rendered attendance block back."""
    access = require_dojo_access(request, dojo_id, TAKE_ATTENDANCE)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)

    if request.method == "POST":
        event.registration_set.filter(waiting_list=False).update(attended=True)

    if request.headers.get("HX-Request"):
        return render(request, "dojos/partials/_attendance.html", {"dojo": dojo, "dojo_access": access, **_attendance_context(event)})
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)


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
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
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
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
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
