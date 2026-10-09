"""The engagement snapshot (DATA_MODEL.md §11, "Engagement snapshot"):
how each ninja comes to sessions, measured against the sessions their dojo
actually ran, so a regular at a monthly dojo is as regular as one at a
weekly dojo. rebuild() recomputes every NinjaEngagement row and records
each overall stage change as a NinjaEngagementChange (what journeys
trigger on); the rebuild_engagement task runs it nightly.

- Offered: sessions that aren't drafts, have started, and were meant for
  the ninja (is_aimed_at: age range; a girls' session only for girls).
  A boy who skips a girls' session hasn't missed anything.
- Came: marked present. At a session where the dojo marked nobody at all,
  a confirmed place counts instead; otherwise dojos that don't take
  attendance would make every child look lapsed (from_marked_attendance
  records when that happened).
- The stage, first match wins: aged out, never came, new, lapsed, at risk,
  regular, occasional. The thresholds are the constants below (decided
  2026-09-25 as a starting point: regular = at least 3 visits and half the
  sessions offered in 180 days; at risk = the last 3 offered missed).
"""

from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Ninja, age_on
from dojos.models import Dojo

from .models import Event, NinjaEngagement, NinjaEngagementChange, Registration

WINDOW_DAYS = 180
HISTORY_DAYS = 365
NEW_DAYS = 60
NEW_MAX_VISITS = 2
REGULAR_MIN_VISITS = 3
REGULAR_MIN_RATE = 0.5
AT_RISK_MISSED = 3
NO_SHOW_DAYS = 90
ADULT_AGE = 18


def is_aimed_at(ninja, event):
    """Whether `event` was meant for `ninja`: statistics only, it never
    restricts who can sign up."""
    if event.audience == Event.GIRLS and ninja.gender != Ninja.GIRL:
        return False
    if ninja.date_of_birth is not None:
        age = age_on(ninja.date_of_birth, timezone.localtime(event.start_time).date())
        if event.min_age is not None and age < event.min_age:
            return False
        if event.max_age is not None and age > event.max_age:
            return False
    return True


def stage(*, age, dojo_max_age, attended_total, first_attended, last_attended, attended_window, rate, missed, today):
    if age is not None and (age >= ADULT_AGE or (dojo_max_age is not None and age > dojo_max_age)):
        return NinjaEngagement.AGED_OUT
    if attended_total == 0:
        return NinjaEngagement.NEVER_ATTENDED
    recent = today - timedelta(days=WINDOW_DAYS)
    if first_attended >= today - timedelta(days=NEW_DAYS) or (
        attended_total <= NEW_MAX_VISITS and last_attended >= recent
    ):
        return NinjaEngagement.NEW
    if attended_window == 0:
        return NinjaEngagement.LAPSED
    if missed >= AT_RISK_MISSED:
        return NinjaEngagement.AT_RISK
    if attended_window >= REGULAR_MIN_VISITS and rate >= REGULAR_MIN_RATE:
        return NinjaEngagement.REGULAR
    return NinjaEngagement.OCCASIONAL


def _aimed_sessions(ninja, dojo, sessions, history_start):
    """The sessions `dojo` ran in the history window that were meant for `ninja`."""
    if dojo is None:
        return []
    return [s for s in sessions.get(dojo.pk, []) if s.start_time >= history_start and is_aimed_at(ninja, s)]


def _missed_in_a_row(aimed, counted, visits):
    """Sessions offered since the last visit, newest first, until a visit."""
    last_visit = max((visits[pk].start_time for pk in counted), default=None)
    missed = 0
    for session in sorted(aimed, key=lambda s: s.start_time, reverse=True):
        if session.pk in counted or (last_visit is not None and session.start_time <= last_visit):
            break
        missed += 1
    return missed


def _metrics(ninja, dojo, sessions, visits, no_shows, now, overall):
    """Window figures for one ninja at one dojo. `visits` maps event id to
    the events the ninja came to (anywhere). For the overall row, `dojo` is
    the main dojo and a visit anywhere counts: sessions they came to at
    another dojo count as offered, and a visit anywhere ends a run of
    missed sessions."""
    window_start = now - timedelta(days=WINDOW_DAYS)
    aimed = _aimed_sessions(ninja, dojo, sessions, now - timedelta(days=HISTORY_DAYS))
    offered = {s.pk for s in aimed if s.start_time >= window_start}
    counted = {pk for pk, event in visits.items() if overall or event.dojo_id == dojo.pk}
    recent_visits = {pk for pk in counted if visits[pk].start_time >= window_start}
    if overall:
        offered |= recent_visits
    attended_window = len(offered & recent_visits)
    no_show_since = now - timedelta(days=NO_SHOW_DAYS)
    return {
        "offered_180d": len(offered),
        "attended_180d": attended_window,
        "attendance_rate": min(1.0, attended_window / len(offered)) if offered else 0.0,
        "missed_in_a_row": _missed_in_a_row(aimed, counted, visits),
        "no_shows_90d": sum(
            1 for s in no_shows if (overall or s.dojo_id == dojo.pk) and s.start_time >= no_show_since
        ),
    }


def _row(ninja, dojo, main, overall, visits, sessions, no_shows, upcoming, today, now):
    """One NinjaEngagement row: at `dojo`, or overall (measured at `main`)."""
    counted = {pk: v for pk, v in visits.items() if overall or v[0].dojo_id == dojo.pk}
    days = sorted(timezone.localtime(event.start_time).date() for event, _marked in counted.values())
    measured_at = main if overall else dojo
    metrics = _metrics(ninja, measured_at, sessions, {pk: v[0] for pk, v in visits.items()}, no_shows, now, overall)
    first, last = (days[0], days[-1]) if days else (None, None)
    age = age_on(ninja.date_of_birth, today) if ninja.date_of_birth else None
    return NinjaEngagement(
        ninja=ninja,
        dojo=None if overall else dojo,
        main_dojo=main,
        stage=stage(
            age=age,
            dojo_max_age=measured_at.max_age if measured_at else None,
            attended_total=len(days),
            first_attended=first,
            last_attended=last,
            attended_window=metrics["attended_180d"],
            rate=metrics["attendance_rate"],
            missed=metrics["missed_in_a_row"],
            today=today,
        ),
        first_attended=first,
        last_attended=last,
        attended_total=len(days),
        has_upcoming=bool(upcoming) if overall else dojo.pk in upcoming,
        from_marked_attendance=all(marked for _event, marked in counted.values()),
        computed_on=today,
        **metrics,
    )


def _sessions_by_dojo(events, now, history_start):
    """{dojo_id: [event]}: the sessions each dojo ran in the history window,
    taken from `events` (_sessions_by_id), so each session is one object."""
    sessions = defaultdict(list)
    for event in events.values():
        if history_start <= event.start_time <= now:
            sessions[event.dojo_id].append(event)
    return sessions


def _sessions_by_id(dojos):
    """{event_id: event} for every session that isn't a draft, each with its
    dojo from `dojos` attached. Every session is loaded once and shared by
    its registrations: a select_related on the registrations would build a
    new Event and Dojo for each one."""
    events = Event.objects.select_related(None).exclude(status=Event.DRAFT).in_bulk()
    for event in events.values():
        event.dojo = dojos[event.dojo_id]
    return events


def _marked_events():
    """The sessions where the dojo marked anyone's attendance."""
    return set(Registration.objects.filter(attended__isnull=False).values_list("event_id", flat=True))


def _registrations_by_ninja(now, dojos, events=None, marked_events=None, ninjas=None):
    """Each child's registrations, sorted into what came of them:
    came {ninja_id: {event_id: (event, marked)}}, no_shows {ninja_id: [event]}
    and upcoming {ninja_id: {dojo_id}}. The registrations are read as plain
    values, a chunk at a time, and point at shared event objects, so the
    memory follows the number of sessions rather than of registrations.
    `ninjas` (first id, last id) limits it to one batch of children; a
    batched rebuild passes `events` and `marked_events` in, loaded once."""
    if events is None:
        events = _sessions_by_id(dojos)
    if marked_events is None:
        marked_events = _marked_events()
    came, no_shows, upcoming = defaultdict(dict), defaultdict(list), defaultdict(set)
    rows = Registration.objects.exclude(event__status=Event.DRAFT)
    if ninjas is not None:
        rows = rows.filter(ninja_id__gte=ninjas[0], ninja_id__lte=ninjas[1])
    for ninja_id, event_id, attended, waiting_list in rows.values_list(
        "ninja_id", "event_id", "attended", "waiting_list"
    ).iterator(chunk_size=2000):
        event = events[event_id]
        if event.start_time > now:
            if not waiting_list:
                upcoming[ninja_id].add(event.dojo_id)
        elif attended is True:
            came[ninja_id][event_id] = (event, True)
        elif attended is None and not waiting_list and event_id not in marked_events:
            came[ninja_id][event_id] = (event, False)
        elif attended is False:
            no_shows[ninja_id].append(event)
    return came, no_shows, upcoming


def _main_dojo(ninja, visits, history_start):
    """(main dojo, {dojo_id: dojo} to measure at): the home dojo, else the one
    visited most in the history window, else the last one visited."""
    recent = [event for event, _marked in visits.values() if event.start_time >= history_start]
    dojos = {event.dojo_id: event.dojo for event in recent}
    busiest = Counter(event.dojo_id for event in recent).most_common(1)
    main = ninja.home_dojo or (dojos[busiest[0][0]] if busiest else None)
    if main is None and visits:
        main = max(visits.values(), key=lambda v: v[0].start_time)[0].dojo
    if main is not None:
        dojos.setdefault(main.pk, main)
    return main, dojos


def _stage_changes(rows, today, ninjas):
    """A NinjaEngagementChange for every child in the batch `ninjas` (first
    id, last id) whose overall stage moved."""
    previous = dict(
        NinjaEngagement.objects.filter(
            dojo__isnull=True, ninja_id__gte=ninjas[0], ninja_id__lte=ninjas[1]
        ).values_list("ninja_id", "stage")
    )
    return [
        NinjaEngagementChange(ninja=row.ninja, from_stage=previous[row.ninja.pk], to_stage=row.stage, changed_on=today)
        for row in rows
        if row.dojo is None and row.ninja.pk in previous and previous[row.ninja.pk] != row.stage
    ]


def _rebuild_batch(ninjas, *, now, today, history_start, sessions, every_dojo, events, marked_events):
    """Recompute the rows of the children with an id in `ninjas` (first,
    last) and replace theirs, in one transaction. Returns how many rows."""
    came, no_shows, upcoming = _registrations_by_ninja(
        now, every_dojo, events=events, marked_events=marked_events, ninjas=ninjas
    )
    rows = []
    for ninja in Ninja.objects.select_related(None).filter(pk__gte=ninjas[0], pk__lte=ninjas[1]):
        if ninja.home_dojo_id is not None:
            ninja.home_dojo = every_dojo[ninja.home_dojo_id]
        visits = came.get(ninja.pk, {})
        main, dojos = _main_dojo(ninja, visits, history_start)
        shared = {
            "visits": visits,
            "sessions": sessions,
            "no_shows": no_shows.get(ninja.pk, []),
            "upcoming": upcoming.get(ninja.pk, set()),
            "today": today,
            "now": now,
        }
        rows.append(_row(ninja, None, main, True, **shared))
        rows.extend(_row(ninja, dojo, main, False, **shared) for dojo in dojos.values())

    changes = _stage_changes(rows, today, ninjas)
    with transaction.atomic():
        NinjaEngagement.objects.filter(ninja_id__gte=ninjas[0], ninja_id__lte=ninjas[1]).delete()
        NinjaEngagement.objects.bulk_create(rows, batch_size=500)
        # Rebuilding twice on a day doesn't record the same change twice.
        NinjaEngagementChange.objects.filter(changed_on=today, ninja_id__in=[c.ninja_id for c in changes]).delete()
        NinjaEngagementChange.objects.bulk_create(changes, batch_size=500)
    return len(rows)


def rebuild(today=None, batch_size=None):
    """Recompute every NinjaEngagement row, `batch_size` children at a time
    (default settings.ENGAGEMENT_REBUILD_BATCH_SIZE)
    (CAPACITY.md, "Load: Celery workers and mail"): each batch reads only
    its children's registrations and is written in its own transaction, so
    the memory follows the batch, not the number of children. While it
    runs, children already done show their new stage and the others last
    night's. Returns how many rows it wrote."""
    batch_size = batch_size or settings.ENGAGEMENT_REBUILD_BATCH_SIZE
    now = timezone.now()
    today = today or timezone.localdate()
    history_start = now - timedelta(days=HISTORY_DAYS)
    # Every dojo and session once, shared by every batch, the children's home
    # dojos and their registrations (a select_related would give each row its
    # own copy).
    every_dojo = Dojo.objects.in_bulk()
    events = _sessions_by_id(every_dojo)
    context = {
        "now": now,
        "today": today,
        "history_start": history_start,
        "sessions": _sessions_by_dojo(events, now, history_start),
        "every_dojo": every_dojo,
        "events": events,
        "marked_events": _marked_events(),
    }
    ids = list(Ninja.objects.order_by("pk").values_list("pk", flat=True))
    written = 0
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        written += _rebuild_batch((batch[0], batch[-1]), **context)
    return written
