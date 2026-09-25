import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.models import Ninja, User
from applications.services import is_approved_champion
from content.models import FAQ, OrganisationTeamMember
from events.awards import BeltError, award_belt, sync_milestones
from events.forms import EventForm
from events.models import Belt, Event, Registration
from geo.geocoding import find_province, geocode
from notifications.models import Notification
from pathways.models import Pathway

from . import team
from .access import (
    AWARD_BELTS,
    EDIT_SETTINGS,
    MANAGE_EVENTS,
    MANAGE_LIFECYCLE,
    MANAGE_TEAM,
    POST_UPDATES,
    TAKE_ATTENDANCE,
    accessible_dojos,
    is_approved_mentor,
    require_dojo_access,
)
from .forms import AnnouncementForm, DojoCreateForm, DojoProfileForm, DojoSearchForm
from .models import Dojo, DojoMembership
from .search import attach_next_events, dojos_by_distance, resolve_search_origin

RESULTS_PER_PAGE = 20
WIDGET_RESULTS_LIMIT = 5
NOTIFICATION_LIMIT = 10
# How many of a dojo's newest updates its public page shows ("From this dojo").
PUBLIC_UPDATES_LIMIT = 5


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
    origin, search_label, geocode_failed = resolve_search_origin(form, request.user)
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
    origin, search_label, geocode_failed = resolve_search_origin(form, request.user)
    dojos = attach_next_events(list(dojos_by_distance(origin)[:WIDGET_RESULTS_LIMIT]))

    return render(request, "dojos/partials/_dojo_finder_widget_results.html", {
        "dojos": dojos,
        "search_label": search_label,
        "geocode_failed": geocode_failed,
    })


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
    dojo = get_object_or_404(Dojo.objects.public(), id=dojo_id)
    next_event = dojo.event_set.visible().filter(start_time__gte=timezone.now()).order_by("start_time").first()
    faqs = FAQ.objects.for_dojo(dojo)
    return render(request, "dojos/dojo_detail.html", {
        "dojo": dojo, "next_event": next_event, "faqs": faqs,
        "announcements": dojo.announcements.all()[:PUBLIC_UPDATES_LIMIT],
        "mentors": dojo.memberships.for_team_page(),
        "join_state": _join_state(request.user, dojo),
    })


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
            messages.success(request, f"Your request to join {dojo.name} has been sent to its team.")
        except team.TeamError as error:
            messages.error(request, str(error))
    return redirect("dojo_detail", dojo_id=dojo.id)


def _attendance_context(event):
    """What dojos/partials/_attendance.html needs for one event: its
    confirmed (not waitlisted) registrations, alphabetical, plus how many
    are already marked present. Shared by the dashboard, the per-event
    attendance page and the htmx endpoints that re-render parts of it."""
    registrations = list(
        event.registration_set.filter(waiting_list=False)
        .select_related("ninja")
        .prefetch_related("pathways", "ninja__belts__belt")
        .order_by("ninja__name")
    )
    event_pathway_ids = set(event.pathways.values_list("id", flat=True))
    return {
        "event": event,
        "registrations": registrations,
        "present_count": sum(1 for r in registrations if r.attended),
        # For each row's pathway picker: every pathway, the session's own first.
        "event_pathway_ids": event_pathway_ids,
        "all_pathways": sorted(Pathway.objects.all(), key=lambda p: (p.id not in event_pathway_ids, p.name)),
        # For each row's "Award belt" picker (only belts above the ninja's current one are offered).
        "all_belts": list(Belt.objects.all()),
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
        "dormancy_nudge": team.needs_dormancy_nudge(dojo),
        **(_attendance_context(session) if session is not None else {}),
        "active": "attendance",
        **_admin_context(request, access),
    })


def _geocode_address(dojo):
    """Set dojo.location (and province) from dojo.address. Tolerant: a failed
    or no-match geocode never blocks a save — returns False and leaves the
    location as it was (same pattern as dojos.search.resolve_search_origin)."""
    try:
        coords = geocode(dojo.address)
    except requests.RequestException:
        coords = None
    if not coords:
        return False
    lat, lon = coords
    dojo.location = Point(lon, lat, srid=4326)
    dojo.province = find_province(dojo.location)
    return True


@login_required
def dojo_create(request):
    """An approved champion creates a dojo (DATA_MODEL.md §10): it starts as
    a draft, hidden from the public site, with them as its champion. They
    fill in the rest on the Settings page and launch it from there."""
    if not is_approved_champion(request.user):
        messages.error(request, "Only approved champions with a valid background check can create a dojo.")
        return redirect("account_home")

    if request.method == "POST":
        form = DojoCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                dojo = form.save(commit=False)
                dojo.status = Dojo.DRAFT
                dojo.created_by = request.user
                geocode_failed = bool(dojo.address) and not _geocode_address(dojo)
                dojo.save()
                DojoMembership.objects.create(
                    dojo=dojo, user=request.user, role=DojoMembership.CHAMPION,
                    status=DojoMembership.ACTIVE, joined_at=timezone.now(), requested_by=request.user,
                )
            messages.success(request, f"{dojo.name} has been created as a draft. Fill in its profile, then launch it.")
            if geocode_failed:
                messages.error(request, "We couldn't find that address on the map; check it on this page.")
            return redirect("dojo_manage", dojo_id=dojo.id)
    else:
        form = DojoCreateForm()
    return render(request, "dojos/dojo_create.html", {"form": form})


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
                geocode_failed = not _geocode_address(dojo)

            dojo.save()
            form.save_m2m()  # pathways — commit=False above skipped them
            saved = True
    else:
        form = DojoProfileForm(instance=dojo)

    return render(request, "dojos/dojo_manage.html", {
        "form": form, "saved": saved, "geocode_failed": geocode_failed, "active": "settings",
        "active_event_count": team.active_events(dojo).count(),
        **_admin_context(request, access),
    })


@login_required
def dojo_set_lifecycle(request, dojo_id):
    """The champion's lifecycle buttons on the settings page (POST only):
    launch, go dormant, restart, archive, reopen — see dojos.team for the
    rules (no active events before dormant/archived, etc.)."""
    access = require_dojo_access(request, dojo_id, MANAGE_LIFECYCLE)
    if request.method == "POST":
        try:
            team.change_status(access.dojo, request.POST.get("action", ""))
            messages.success(request, f"{access.dojo.name} is now {access.dojo.get_status_display().lower()}.")
        except team.TeamError as error:
            messages.error(request, str(error))
    return redirect("dojo_manage", dojo_id=access.dojo.id)


def _youth_mentor_candidates(dojo):
    """Ninja accounts that can be promoted to youth mentor here: ninjas with
    their own login whose home dojo this is, or who've signed up for one of
    its sessions, and who aren't already on the team."""
    on_team = dojo.memberships.active().values("user_id")
    ninjas = (
        Ninja.objects.exclude(account=None)
        .filter(Q(home_dojo=dojo) | Q(registration__event__dojo=dojo))
        .exclude(account_id__in=on_team)
        .select_related("account")
        .distinct()
        .order_by("name")
    )
    return ninjas


@login_required
def dojo_updates(request, dojo_id):
    """The admin sidebar's "Updates" page: the dojo's "From this dojo"
    updates (content.Announcement), newest first, and with POST_UPDATES a
    form to post a new one, dated today."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    form = AnnouncementForm()
    if request.method == "POST":
        if not access.can_post_updates:
            raise PermissionDenied
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.dojo = dojo
            announcement.date = timezone.localdate()
            announcement.save()
            messages.success(request, "Update posted on the dojo's page.")
            return redirect("dojo_updates", dojo_id=dojo.id)
    return render(request, "dojos/dojo_updates.html", {
        "form": form,
        "announcements": dojo.announcements.all(),
        "public_limit": PUBLIC_UPDATES_LIMIT,
        "active": "updates",
        **_admin_context(request, access),
    })


@login_required
def dojo_update_delete(request, dojo_id, announcement_id):
    """Remove one update (POST only, POST_UPDATES)."""
    access = require_dojo_access(request, dojo_id, POST_UPDATES)
    if request.method == "POST":
        get_object_or_404(access.dojo.announcements, id=announcement_id).delete()
        messages.success(request, "Update removed.")
    return redirect("dojo_updates", dojo_id=access.dojo.id)


@login_required
def dojo_team_manage(request, dojo_id):
    """The admin sidebar's "Team" page: the dojo's team, pending join
    requests, and (for MANAGE_TEAM) the forms to act on them."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    memberships = dojo.memberships.select_related("user", "promoted_by__user")
    return render(request, "dojos/dojo_team_manage.html", {
        "active_members": memberships.filter(status=DojoMembership.ACTIVE).order_by("role", "user__first_name"),
        "requests": memberships.filter(status=DojoMembership.REQUESTED).order_by("created_at"),
        "former_members": memberships.filter(status=DojoMembership.DORMANT).order_by("-left_at"),
        "transfer_candidates": memberships.filter(
            status=DojoMembership.ACTIVE, role=DojoMembership.MENTOR,
        ).order_by("user__first_name"),
        "youth_mentor_candidates": _youth_mentor_candidates(dojo) if access.can_manage_team else [],
        "active": "team",
        **_admin_context(request, access),
    })


@login_required
def dojo_team_action(request, dojo_id):
    """Every change posted from the Team page (POST only; `action` says which):
    accept / decline a request, add a mentor (by email), promote a ninja to
    youth mentor, remove a member, leave, and transfer the champion role.
    Leaving is open to any team manager; transfer is champion-only; the rest
    need MANAGE_TEAM."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    if request.method != "POST":
        return redirect("dojo_team_manage", dojo_id=dojo.id)

    action = request.POST.get("action", "")
    membership = None
    if request.POST.get("membership_id"):
        membership = get_object_or_404(DojoMembership, id=request.POST["membership_id"], dojo=dojo)

    try:
        if action == "leave":
            team.leave(access.membership)
            messages.success(request, f"You've left the {dojo.name} team.")
            return redirect("account_home")
        if action == "transfer":
            if not access.is_champion or membership is None:
                raise PermissionDenied
            team.transfer_champion(dojo, access.membership, membership)
            messages.success(request, f"{membership.name} is now the champion of {dojo.name}.")
            return redirect("dojo_team_manage", dojo_id=dojo.id)

        if not access.can_manage_team:
            raise PermissionDenied
        if action in ("accept", "decline", "remove") and membership is None:
            raise Http404
        if action == "accept":
            team.accept_request(membership, by=request.user)
            messages.success(request, f"{membership.name} is now on the team.")
        elif action == "decline":
            team.decline_request(membership, by=request.user)
            messages.success(request, "Request declined.")
        elif action == "remove":
            team.remove_member(membership)
            messages.success(request, f"{membership.name} has been removed from the team.")
        elif action == "add_mentor":
            email = request.POST.get("email", "").strip()
            user = User.objects.filter(email__iexact=email).first() if email else None
            if user is None:
                raise team.TeamError("No account uses that email address.")
            team.add_mentor(dojo, user, by=request.user)
            messages.success(request, f"{user.team_name} has been added to the team.")
        elif action == "promote":
            ninja = get_object_or_404(_youth_mentor_candidates(dojo), id=request.POST.get("ninja_id"))
            team.promote_youth_mentor(dojo, ninja.account, by_membership=access.membership)
            messages.success(request, f"{ninja.account.team_name} is now a youth mentor.")
        else:
            messages.error(request, "Unknown action.")
    except team.TeamError as error:
        messages.error(request, str(error))
    return redirect("dojo_team_manage", dojo_id=dojo.id)


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
        Registration.objects.select_related("ninja").prefetch_related("pathways"),
        id=registration_id, event=event, waiting_list=False,
    )

    if request.method == "POST" and request.POST.get("attended") in ATTENDANCE_VALUES:
        registration.attended = ATTENDANCE_VALUES[request.POST["attended"]]
        registration.save(update_fields=["attended"])
        # Milestone badges count sessions attended; one that grants a belt
        # awards it as whoever marked the attendance.
        sync_milestones(registration.ninja, access.membership)

    if request.headers.get("HX-Request"):
        context = {"dojo": dojo, "dojo_access": access, **_attendance_context(event), "registration": registration}
        row = render_to_string("dojos/partials/_attendance_row.html", context, request=request)
        summary = render_to_string("dojos/partials/_attendance_summary.html", {**context, "oob": True}, request=request)
        return HttpResponse(row + summary)
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)


@login_required
def dojo_event_registration_pathways(request, dojo_id, event_id, registration_id):
    """Set which pathways a ninja works on at this session (POST `pathway`,
    repeated) — pre-filled from the event's pathways at signup, narrowed
    here by the team. Any pathway may be picked; the event's are just the
    default. Same htmx/no-JS handling as dojo_event_attendance_mark."""
    access = require_dojo_access(request, dojo_id, TAKE_ATTENDANCE)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    registration = get_object_or_404(
        Registration.objects.select_related("ninja"),
        id=registration_id, event=event, waiting_list=False,
    )
    if request.method == "POST":
        registration.pathways.set(Pathway.objects.filter(id__in=request.POST.getlist("pathway")))

    if request.headers.get("HX-Request"):
        context = {
            "dojo": dojo, "dojo_access": access, **_attendance_context(event),
            "registration": Registration.objects.prefetch_related("pathways").get(pk=registration.pk),
        }
        return render(request, "dojos/partials/_attendance_row.html", context)
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)


@login_required
def dojo_event_award_belt(request, dojo_id, event_id, registration_id):
    """Award the ninja on this attendance row a belt (POST `belt`, optional
    `note`), as the viewer's champion/mentor membership. The rules (a belt
    above their current one; see events.awards.award_belt) raise BeltError,
    shown inside the row. Same htmx/no-JS handling as
    dojo_event_attendance_mark."""
    access = require_dojo_access(request, dojo_id, AWARD_BELTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    registration = get_object_or_404(
        Registration.objects.select_related("ninja"),
        id=registration_id, event=event, waiting_list=False,
    )
    belt_error = None
    if request.method == "POST":
        belt = Belt.objects.filter(id=request.POST.get("belt") or None).first()
        try:
            if belt is None:
                raise BeltError("Pick a belt to award.")
            award_belt(registration.ninja, belt, access.membership, note=request.POST.get("note", ""))
        except BeltError as error:
            belt_error = str(error)
            if not request.headers.get("HX-Request"):
                messages.error(request, belt_error)

    if request.headers.get("HX-Request"):
        context = {
            "dojo": dojo, "dojo_access": access, **_attendance_context(event), "belt_error": belt_error,
            "registration": Registration.objects.select_related("ninja").prefetch_related("pathways").get(
                pk=registration.pk,
            ),
        }
        return render(request, "dojos/partials/_attendance_row.html", context)
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)


@login_required
def dojo_event_attendance_mark_all(request, dojo_id, event_id):
    """The "Mark all present" button — every confirmed registration for the event. An
    htmx request gets the whole re-rendered attendance block back."""
    access = require_dojo_access(request, dojo_id, TAKE_ATTENDANCE)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)

    if request.method == "POST":
        confirmed = event.registration_set.filter(waiting_list=False)
        confirmed.update(attended=True)
        for ninja in Ninja.objects.filter(registration__in=confirmed):
            sync_milestones(ninja, access.membership)

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


def team_member_detail(request, member_id):
    """The organisation's team details page for one listed person
    (content.OrganisationTeamMember — display only, e.g. "Member of the
    board"). A dojo's own team is shown on dojo_team.html instead."""
    member = get_object_or_404(OrganisationTeamMember, id=member_id, is_public=True)
    return render(request, "dojos/team_member_detail.html", {
        "mentor": member, "focus_areas": member.focus_area_list,
    })
