"""The API, version 1 (DATA_MODEL.md §13), at /api/v1/, reference at
/api/v1/docs. For now: a dojo's sessions and their attendance, for an app
at the door. Every call works for the calling client's own dojo only
(another dojo's session is a 404) and goes through the same code as the
dojo team's attendance list (events.attendance). Changes are recorded in
the audit log with the client's technical account as the actor. Health
notes and other sensitive fields are never part of it (api.tests checks
the schema against the privacy classification)."""

from datetime import datetime, time
from typing import Literal

from auditlog.context import set_actor
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI, Schema

from events import attendance
from events.models import Event

from .auth import TOKEN_URL, ClientRateThrottle, OAuth2
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
    name: str
    start_time: datetime
    end_time: datetime
    status: str
    places: int


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
        name=event.name,
        start_time=event.start_time,
        end_time=event.end_time,
        status=event.status,
        places=event.places,
    )


def _child_out(registration):
    return ChildOut(registration_id=registration.id, name=registration.ninja.name, attended=registration.attended)


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


@api.get("/events", response={200: list[EventOut], **ERRORS}, **read.operation(summary="The dojo's sessions"))
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
