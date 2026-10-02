"""The dashboard and taking attendance (htmx rows, children and the session's
team), with the pathways picked per child and the belts and badges awarded
from the list (events.awards)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from events import attendance
from events.awards import BadgeError, BeltError, award_badge, award_belt
from events.models import Badge, Belt, Event, NinjaEngagement, Registration
from pathways.models import Pathway

from .. import team
from ..access import (
    AWARD_BADGES,
    AWARD_BELTS,
    TAKE_ATTENDANCE,
    require_dojo_access,
)
from ..forms import (
    AwardBadgeForm,
    AwardBeltForm,
)
from .common import _admin_context


def _attendance_context(event):
    """What dojos/partials/_attendance.html needs for one event: its
    confirmed (not waitlisted) registrations, alphabetical, plus how many
    are already marked present. Shared by the dashboard, the per-event
    attendance page and the htmx endpoints that re-render parts of it."""
    registrations = list(
        event.registration_set.filter(waiting_list=False)
        .select_related("ninja", "ninja__home_dojo")
        .prefetch_related("pathways", "ninja__belts__belt", "ninja__badges")
        .order_by("ninja__name", "ninja__family_name")
    )
    event_pathway_ids = set(event.pathways.values_list("id", flat=True))
    team_rows = _team_attendance_rows(event)
    return {
        "event": event,
        "registrations": registrations,
        "present_count": sum(1 for r in registrations if r.attended),
        # The session's team, on the same list (who was there: insurance).
        "team_rows": team_rows,
        "team_present_count": sum(1 for row in team_rows if row["attended"]),
        # For each row's pathway picker: every pathway, the session's own first.
        "event_pathway_ids": event_pathway_ids,
        "all_pathways": sorted(Pathway.objects.all(), key=lambda p: (p.id not in event_pathway_ids, p.name)),
        # Each row's "Award belt" and "Award badge" forms, for a ninja with
        # something left to award: belts above their current one, one-off
        # badges they haven't earned yet.
        "belt_forms": _award_forms(AwardBeltForm, registrations, _awardable_belts(registrations)),
        "badge_forms": _award_forms(AwardBadgeForm, registrations, _awardable_badges(registrations)),
        # How each ninja comes to this dojo (last night's events.engagement snapshot).
        "engagement_by_ninja": {
            row.ninja_id: row
            for row in NinjaEngagement.objects.filter(
                dojo_id=event.dojo_id, ninja_id__in=[r.ninja_id for r in registrations]
            )
        },
    }


def _awardable_belts(registrations):
    belts = list(Belt.objects.all())
    result = {}
    for registration in registrations:
        current = registration.ninja.current_belt
        result[registration.ninja_id] = [belt for belt in belts if not current or belt.level > current.level]
    return result


def _award_forms(form_class, registrations, offers):
    return {
        registration.ninja_id: form_class(registration=registration, offered=offers[registration.ninja_id])
        for registration in registrations
        if offers[registration.ninja_id]
    }


def _awardable_badges(registrations):
    one_offs = list(Badge.objects.filter(kind=Badge.ONE_OFF).order_by("name"))
    result = {}
    for registration in registrations:
        earned = {nb.badge_id for nb in registration.ninja.badges.all() if nb.earned_date}
        result[registration.ninja_id] = [badge for badge in one_offs if badge.id not in earned]
    return result


def _team_attendance_rows(event):
    return attendance.team_rows(event)


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

    return render(
        request,
        "dojos/dojo_dashboard.html",
        {
            "session": session,
            "dormancy_nudge": team.needs_dormancy_nudge(dojo),
            **(_attendance_context(session) if session is not None else {}),
            "active": "attendance",
            **_admin_context(request, access),
        },
    )


ATTENDANCE_VALUES = {"present": True, "absent": False, "none": None}


@login_required
def dojo_event_attendance(request, dojo_id, event_id):
    """Take attendance for one specific session — reached from that event's
    detail page. Same list as the dashboard's (dojos/partials/_attendance.html),
    which only ever shows the next/most recent session."""
    access = require_dojo_access(request, dojo_id, TAKE_ATTENDANCE)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    return render(
        request,
        "dojos/dojo_event_attendance.html",
        {
            **_attendance_context(event),
            "active": "events",
            **_admin_context(request, access),
        },
    )


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
        id=registration_id,
        event=event,
        waiting_list=False,
    )

    if request.method == "POST" and request.POST.get("attended") in ATTENDANCE_VALUES:
        # Milestone badges count sessions attended; one that grants a belt
        # awards it as whoever marked the attendance.
        attendance.mark_child(registration, ATTENDANCE_VALUES[request.POST["attended"]], awarded_as=access.membership)

    if request.headers.get("HX-Request"):
        context = {"dojo": dojo, "dojo_access": access, **_attendance_context(event), "registration": registration}
        row = render_to_string("dojos/partials/_attendance_row.html", context, request=request)
        summary = render_to_string(
            "dojos/partials/_attendance_summary.html", {**context, "oob": True}, request=request
        )
        return HttpResponse(row + summary)
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)


@login_required
def dojo_event_team_attendance_mark(request, dojo_id, event_id, membership_id):
    """Present/absent/none for one person on the session's team (POST
    `attended`), same toggle as a ninja's row. htmx gets the row back plus
    the team count out-of-band; a plain post redirects to the attendance page."""
    access = require_dojo_access(request, dojo_id, TAKE_ATTENDANCE)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    membership = get_object_or_404(event.team.select_related("user"), id=membership_id)

    if request.method == "POST" and request.POST.get("attended") in ATTENDANCE_VALUES:
        attendance.mark_team_member(event, membership, ATTENDANCE_VALUES[request.POST["attended"]], request.user)

    if request.headers.get("HX-Request"):
        context = {"dojo": dojo, "dojo_access": access, **_attendance_context(event)}
        row = next(r for r in context["team_rows"] if r["membership"].id == membership.id)
        html = render_to_string("dojos/partials/_attendance_team_row.html", {**context, "row": row}, request=request)
        summary = render_to_string(
            "dojos/partials/_attendance_summary.html", {**context, "oob": True}, request=request
        )
        return HttpResponse(html + summary)
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
        id=registration_id,
        event=event,
        waiting_list=False,
    )
    if request.method == "POST":
        registration.pathways.set(Pathway.objects.filter(id__in=request.POST.getlist("pathway")))

    if request.headers.get("HX-Request"):
        context = {
            "dojo": dojo,
            "dojo_access": access,
            **_attendance_context(event),
            "registration": Registration.objects.prefetch_related("pathways").get(pk=registration.pk),
        }
        return render(request, "dojos/partials/_attendance_row.html", context)
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)


def _award_view(request, access, event_id, registration_id, form_class, forms_key, award, error_class):
    """The "Award belt" / "Award badge" forms on an attendance row: the rules
    (events.awards) raise `error_class`, shown under the field in the
    re-rendered row. Same htmx/no-JS handling as dojo_event_attendance_mark."""
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    registration = get_object_or_404(
        Registration.objects.select_related("ninja"),
        id=registration_id,
        event=event,
        waiting_list=False,
    )
    form = None
    if request.method == "POST":
        form = form_class(request.POST, registration=registration, offered=[])
        if form.is_valid():
            try:
                award(
                    registration.ninja,
                    form.cleaned_data[form.field],
                    access.membership,
                    note=form.cleaned_data["note"],
                )
            except error_class as error:
                form.add_error(form.field, str(error))
        if form.errors and not request.headers.get("HX-Request"):
            messages.error(request, " ".join(error for errors in form.errors.values() for error in errors))

    if request.headers.get("HX-Request"):
        context = {
            "dojo": dojo,
            "dojo_access": access,
            **_attendance_context(event),
            "registration": Registration.objects.select_related("ninja")
            .prefetch_related("pathways")
            .get(
                pk=registration.pk,
            ),
        }
        if form is not None and form.errors:
            # The posted form, with its error, offering what the row offers
            # now (maybe nothing: the error still shows, until the next load).
            fresh = context[forms_key].get(registration.ninja_id)
            form.offer(fresh.offered if fresh else [])
            context[forms_key][registration.ninja_id] = form
        return render(request, "dojos/partials/_attendance_row.html", context)
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)


@login_required
def dojo_event_award_belt(request, dojo_id, event_id, registration_id):
    """Award the ninja on this attendance row a belt (AwardBeltForm), as the
    viewer's champion/mentor membership: only a belt above their current one
    (events.awards.award_belt)."""
    access = require_dojo_access(request, dojo_id, AWARD_BELTS)
    return _award_view(request, access, event_id, registration_id, AwardBeltForm, "belt_forms", award_belt, BeltError)


@login_required
def dojo_event_award_badge(request, dojo_id, event_id, registration_id):
    """Award the ninja on this attendance row a one-off badge (AwardBadgeForm),
    as the viewer's champion/mentor membership. The organisation defines the
    badges (events.manage); the rules are in events.awards.award_badge."""
    access = require_dojo_access(request, dojo_id, AWARD_BADGES)
    return _award_view(
        request, access, event_id, registration_id, AwardBadgeForm, "badge_forms", award_badge, BadgeError
    )


@login_required
def dojo_event_attendance_mark_all(request, dojo_id, event_id):
    """The "Mark all present" button — every confirmed registration for the
    event, and everyone on its team. An htmx request gets the whole
    re-rendered attendance block back."""
    access = require_dojo_access(request, dojo_id, TAKE_ATTENDANCE)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)

    if request.method == "POST":
        attendance.mark_all_present(event, request.user, awarded_as=access.membership)

    if request.headers.get("HX-Request"):
        return render(
            request,
            "dojos/partials/_attendance.html",
            {"dojo": dojo, "dojo_access": access, **_attendance_context(event)},
        )
    return redirect("dojo_event_attendance", dojo_id=dojo.id, event_id=event.id)
