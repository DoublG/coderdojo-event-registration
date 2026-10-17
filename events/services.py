"""A dojo's sessions: the rules a session must meet, changing its status, and
syncing a planned year from a spreadsheet (DATA_MODEL_API.md §13, decision 6).
Shared by the dojo's event pages (events.forms.EventForm,
dojos.views.event_pages) and the API (api.v1, `POST /events/sync`), so the
two never drift apart.

The sync matches sessions on `Event.external_ref`, a key the spreadsheet
makes once per row and sends on every run: a known key updates its session,
a new one creates a draft. Every row is saved on its own, so one bad row
never stops the others, and the sync never deletes a session."""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Event

if TYPE_CHECKING:
    from dojos.models import Dojo

# At most this many rows per sync call: a year of twice-weekly sessions, with room to spare.
SYNC_LIMIT = 200

CREATED = "created"
UPDATED = "updated"
UNCHANGED = "unchanged"
SKIPPED = "skipped"
ERROR = "error"

# The fields a sync sets; everything else (description, image, team,
# pathways, translations) stays as the dojo's team set it on the site.
SYNCED_FIELDS = ("name", "start_time", "end_time", "places", "venue_name", "min_age", "max_age", "audience")


def session_problems[When: (datetime, time)](
    *,
    start: When | None,
    end: When | None,
    places: int | None,
    min_age: int | None,
    max_age: int | None,
    registers_externally: bool = False,
) -> dict[str, str]:
    """What's wrong with a session's times, places and ages, as {field: message}
    (empty when it's fine). `start` and `end` are both datetimes, or both times
    of the same day. A session that takes its registrations on another website
    may have no places."""
    problems = {}
    if start is not None and end is not None and end <= start:
        problems["end_time"] = _("End time must be after the start time.")
    if places is not None and places < 1 and not registers_externally:
        problems["places"] = _("A session needs at least one place.")
    if min_age is not None and max_age is not None and min_age > max_age:
        problems["max_age"] = _("The maximum age can't be below the minimum age.")
    return problems


def set_status(event: Event, status: str) -> bool:
    """Any status to any other (draft, open, closed): not a one-way
    lifecycle, and registrations are kept either way. Returns whether it
    changed; an unknown status changes nothing."""
    if status not in dict(Event.STATUS_CHOICES) or status == event.status:
        return False
    event.status = status
    event.save(update_fields=["status"])
    return True


@dataclass(frozen=True)
class PlannedSession:
    """One row of a planning spreadsheet, already parsed (api.forms). A blank
    `status` keeps an existing session's status, and makes a new one a draft."""

    external_ref: str
    name: str
    date: date
    start_time: time
    end_time: time
    places: int
    venue_name: str = ""
    min_age: int | None = None
    max_age: int | None = None
    audience: str = Event.EVERYONE
    status: str = ""


@dataclass(frozen=True)
class SyncResult:
    external_ref: str
    outcome: str  # CREATED, UPDATED, UNCHANGED, SKIPPED or ERROR
    event_id: int | None = None
    detail: str = ""


def _values(session: PlannedSession) -> dict[str, Any]:
    return {
        "name": session.name,
        "start_time": timezone.make_aware(datetime.combine(session.date, session.start_time)),
        "end_time": timezone.make_aware(datetime.combine(session.date, session.end_time)),
        "places": session.places,
        "venue_name": session.venue_name,
        "min_age": session.min_age,
        "max_age": session.max_age,
        "audience": session.audience or Event.EVERYONE,
    }


def _sync_one(dojo: "Dojo", session: PlannedSession, now: datetime) -> SyncResult:
    ref = session.external_ref
    values = _values(session)
    problems = session_problems(
        start=values["start_time"],
        end=values["end_time"],
        places=values["places"],
        min_age=values["min_age"],
        max_age=values["max_age"],
    )
    if problems:
        return SyncResult(ref, ERROR, detail=" ".join(problems.values()))

    event = Event.objects.select_for_update().filter(dojo=dojo, external_ref=ref).first()
    if event is None:
        if values["start_time"] <= now:
            return SyncResult(ref, ERROR, detail=_("This session would be in the past."))
        event = Event(dojo=dojo, external_ref=ref, status=session.status or Event.DRAFT, **values)
        try:
            with transaction.atomic():
                event.save()
        except IntegrityError:
            # The same key, created by another call at the same moment.
            return SyncResult(ref, ERROR, detail=_("This session was just created by another call: try again."))
        # A new session covers its dojo's pathways, as on the site (EventForm).
        event.pathways.set(dojo.pathways.all())
        return SyncResult(ref, CREATED, event.id)

    if event.start_time <= now:
        return SyncResult(
            ref, SKIPPED, event.id, _("This session has already started: change it on the site if needed.")
        )
    if values["start_time"] <= now:
        return SyncResult(ref, ERROR, event.id, _("This session would be in the past."))
    changed = [field for field in SYNCED_FIELDS if getattr(event, field) != values[field]]
    if session.status and session.status != event.status:
        changed.append("status")
    if not changed:
        return SyncResult(ref, UNCHANGED, event.id)
    for field in changed:
        setattr(event, field, session.status if field == "status" else values[field])
    event.save()  # a full save(): the audit log records it, the caches are cleared
    return SyncResult(ref, UPDATED, event.id)


def sync_sessions(dojo: "Dojo", sessions: list[PlannedSession]) -> list[SyncResult]:
    """Creates or updates `dojo`'s sessions from planned rows, matched on
    `external_ref`, each row in its own transaction. Never deletes: a row
    left out of the spreadsheet changes nothing. A session that has already
    started is left alone (SKIPPED), and a row whose key came earlier in the
    same call is an error. Returns one result per row, in their order."""
    now = timezone.now()
    seen: set[str] = set()
    results = []
    for session in sessions:
        if session.external_ref in seen:
            results.append(
                SyncResult(session.external_ref, ERROR, detail=_("This key is used by an earlier row too."))
            )
            continue
        seen.add(session.external_ref)
        with transaction.atomic():
            results.append(_sync_one(dojo, session, now))
    return results
