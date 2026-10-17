"""The API, version 1 (DATA_MODEL.md §13), at /api/v1/, reference at
/api/v1/docs. For now: a dojo's sessions and their attendance, for an app
at the door, and syncing the sessions a dojo planned in a spreadsheet.
Every call works for the calling client's own dojo only (another dojo's
session is a 404) and goes through the same code as the dojo team's pages
(events.attendance, events.services). Changes are recorded in
the audit log with the client's technical account as the actor. Health
notes and other sensitive fields are never part of it (api.tests checks
the schema against the privacy classification)."""

from datetime import datetime, time
from typing import Literal

from auditlog.context import set_actor
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Field, NinjaAPI, Schema

from events import attendance, services
from events.models import Event

from .auth import TOKEN_URL, ClientRateThrottle, OAuth2
from .forms import PlannedSessionForm, cell
from .models import DojoApiClient


class ScopedNinjaAPI(NinjaAPI):
    """ninja lists an endpoint's security without scopes (OAuth2.operation
    adds the scoped entry next to it): keep only the scoped one."""

    def get_openapi_schema(self, *args, **kwargs):
        schema = super().get_openapi_schema(*args, **kwargs)
        for operations in schema["paths"].values():
            for operation in operations.values():
                security = operation.get("security")
                if security and any(any(scopes) for entry in security for scopes in entry.values()):
                    operation["security"] = [e for e in security if any(scopes for scopes in e.values())]
        return schema


api = ScopedNinjaAPI(
    version="1",
    title="CoderDojo Belgium API",
    urls_namespace="api-v1",
    description=(
        "For apps and websites that work for one dojo. Log in with OAuth 2.0 client credentials: the "
        "client ID and secret your dojo's champion made on the dojo's API page, exchanged for a token at "
        f"{TOKEN_URL} (see the OAuth2 security scheme). A client only reaches its own dojo, and only with "
        "the scopes it was given."
    ),
    throttle=[ClientRateThrottle(settings.API_RATE_LIMIT)],
)

read = OAuth2(DojoApiClient.READ)
write = OAuth2(DojoApiClient.WRITE)
# Listing sessions predates the events scopes: either one will do.
read_events = OAuth2(DojoApiClient.READ, DojoApiClient.EVENTS_READ)
plan_events = OAuth2(DojoApiClient.EVENTS_WRITE)
EVENTS_LIMIT = 50


class Message(Schema):
    detail: str


# What every endpoint may answer besides its result.
ERRORS = {
    401: Message,  # no token, or an unknown or expired one
    403: Message,  # the token lacks the endpoint's scope
    404: Message,  # not this client's dojo, or no such row
}


class EventOut(Schema):
    id: int
    external_ref: str | None
    name: str
    start_time: datetime
    end_time: datetime
    status: str
    places: int
    venue_name: str
    min_age: int | None
    max_age: int | None
    audience: str


class ChildOut(Schema):
    registration_id: int
    name: str
    attended: bool | None


class TeamMemberOut(Schema):
    membership_id: int
    name: str
    role: str
    attended: bool | None


class AttendanceOut(Schema):
    event: EventOut
    children: list[ChildOut]
    team: list[TeamMemberOut]


class AttendedIn(Schema):
    # true = present, false = absent, null = not marked.
    attended: bool | None


def _event_out(event):
    return EventOut(
        id=event.id,
        external_ref=event.external_ref,
        name=event.name,
        start_time=event.start_time,
        end_time=event.end_time,
        status=event.status,
        places=event.places,
        venue_name=event.venue_name,
        min_age=event.min_age,
        max_age=event.max_age,
        audience=event.audience,
    )


def _child_out(registration):
    return ChildOut(registration_id=registration.id, name=registration.ninja.full_name, attended=registration.attended)


def _team_out(row):
    membership = row["membership"]
    return TeamMemberOut(
        membership_id=membership.id, name=membership.name, role=membership.role, attended=row["attended"]
    )


def _attendance_out(event):
    return AttendanceOut(
        event=_event_out(event),
        children=[_child_out(r) for r in attendance.confirmed_registrations(event)],
        team=[_team_out(row) for row in attendance.team_rows(event)],
    )


def _event(request, event_id):
    return get_object_or_404(Event.objects.filter(dojo=request.auth.dojo), id=event_id)


@api.get("/events", response={200: list[EventOut], **ERRORS}, **read_events.operation(summary="The dojo's sessions"))
def list_events(request, when: Literal["upcoming", "past"] = "upcoming"):
    """Upcoming sessions (from today on, soonest first) or past ones
    (newest first), at most 50."""
    today = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    events = Event.objects.filter(dojo=request.auth.dojo)
    if when == "past":
        events = events.filter(start_time__lt=today).order_by("-start_time")
    else:
        events = events.filter(start_time__gte=today).order_by("start_time")
    return [_event_out(event) for event in events[:EVENTS_LIMIT]]


@api.get(
    "/events/{event_id}/attendance",
    response={200: AttendanceOut, **ERRORS},
    **read.operation(summary="Who has a place, who came"),
)
def get_attendance(request, event_id: int):
    """The children with a confirmed place (not the waiting list) and the
    session's team, each with `attended`: true, false or null (not marked)."""
    return _attendance_out(_event(request, event_id))


@api.put(
    "/events/{event_id}/attendance/children/{registration_id}",
    response={200: ChildOut, **ERRORS},
    **write.operation(summary="Mark a child"),
)
def mark_child(request, event_id: int, registration_id: int, payload: AttendedIn):
    event = _event(request, event_id)
    registration = get_object_or_404(
        attendance.confirmed_registrations(event),
        id=registration_id,
    )
    with set_actor(request.auth.account):
        attendance.mark_child(registration, payload.attended)
    return _child_out(registration)


@api.put(
    "/events/{event_id}/attendance/team/{membership_id}",
    response={200: TeamMemberOut, **ERRORS},
    **write.operation(summary="Mark someone of the team"),
)
def mark_team_member(request, event_id: int, membership_id: int, payload: AttendedIn):
    event = _event(request, event_id)
    membership = get_object_or_404(event.team.select_related("user"), id=membership_id)
    with set_actor(request.auth.account):
        attendance.mark_team_member(event, membership, payload.attended, request.auth.account)
    return _team_out({"membership": membership, "attended": payload.attended})


@api.post(
    "/events/{event_id}/attendance/all-present",
    response={200: AttendanceOut, **ERRORS},
    **write.operation(summary="Mark everyone present"),
)
def mark_all_present(request, event_id: int):
    event = _event(request, event_id)
    with set_actor(request.auth.account):
        attendance.mark_all_present(event, request.auth.account)
    return _attendance_out(event)


# A spreadsheet cell: text or a number, whatever the sheet holds.
Cell = str | int | float | None


class PlannedSessionIn(Schema):
    external_ref: str | int = Field(
        description="The row's own key, made once and sent on every sync (e.g. 2026-W38): the same key updates "
        "the same session. At most 100 characters, unique within the dojo."
    )
    name: Cell = None
    date: Cell = Field(None, description="2026-09-26 or 26/09/2026, or Excel's date number.")
    start_time: Cell = Field(None, description="14:00, or Excel's time (a fraction of a day).")
    end_time: Cell = Field(None, description="Later than start_time, on the same day.")
    places: Cell = Field(None, description="At least 1.")
    venue_name: Cell = Field(None, description="Blank for the dojo's own address.")
    min_age: Cell = None
    max_age: Cell = None
    audience: Cell = Field(None, description="everyone (when blank) or girls.")
    status: Cell = Field(
        None, description="draft, open or closed. Blank keeps the session's status; a new session starts as a draft."
    )


class SyncIn(Schema):
    events: list[PlannedSessionIn] = Field(max_length=services.SYNC_LIMIT)


class SyncRowOut(Schema):
    external_ref: str
    outcome: Literal["created", "updated", "unchanged", "skipped", "error"]
    event_id: int | None
    detail: str


class SyncOut(Schema):
    results: list[SyncRowOut]


@api.post(
    "/events/sync",
    response={200: SyncOut, **ERRORS},
    **plan_events.operation(summary="Add or update planned sessions"),
)
def sync_events(request, payload: SyncIn):
    """Puts the sessions a dojo planned (e.g. a year, in a spreadsheet) on
    the site, at most 200 rows per call. Each row's `external_ref` decides:
    a new key adds a session (a draft, unless `status` says otherwise), a
    known one updates that session. Send every field on every sync: a blank
    venue or age clears it. The description, picture, team and pathways
    stay as set on the site.

    Every row is checked and saved on its own: one bad row never stops the
    others. The answer has one result per row, in the same order, with its
    `outcome`: `created`, `updated`, `unchanged`, `skipped` (the session
    has already started, so the sync leaves it alone) or `error`, and a
    `detail` saying why.
    A row left out of the sheet changes nothing: the sync never deletes."""
    results = []
    forms, sessions = [], []
    for row in payload.events:
        form = PlannedSessionForm({name: cell(value) for name, value in row.dict().items()})
        forms.append(form)
        if form.is_valid():
            sessions.append(form.session())
    with set_actor(request.auth.account):
        synced = iter(services.sync_sessions(request.auth.dojo, sessions))
    for form in forms:
        if form.is_valid():
            result = next(synced)
            results.append(
                SyncRowOut(
                    external_ref=result.external_ref,
                    outcome=result.outcome,
                    event_id=result.event_id,
                    detail=result.detail,
                )
            )
        else:
            results.append(
                SyncRowOut(
                    external_ref=cell(form.data.get("external_ref")),
                    outcome="error",
                    event_id=None,
                    detail=form.problems(),
                )
            )
    return SyncOut(results=results)
