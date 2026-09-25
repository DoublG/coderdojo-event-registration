"""The engagement snapshot (DATA_MODEL.md §11, "Engagement snapshot"):
how each ninja comes to sessions, measured against the sessions their dojo
actually ran, so a regular at a monthly dojo is as regular as one at a
weekly dojo. rebuild() recomputes every NinjaEngagement row; the
rebuild_engagement task runs it nightly.

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

from django.db import transaction
from django.utils import timezone

from accounts.models import Ninja, age_on

from .models import Event, NinjaEngagement, Registration

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


def stage(*, age, dojo_max_age, attended_total, first_attended, last_attended, attended_window, rate, missed,
          today):
    if age is not None and (age >= ADULT_AGE or (dojo_max_age is not None and age > dojo_max_age)):
        return NinjaEngagement.AGED_OUT
    if attended_total == 0:
        return NinjaEngagement.NEVER_ATTENDED
    recent = today - timedelta(days=WINDOW_DAYS)
    if first_attended >= today - timedelta(days=NEW_DAYS) or (
            attended_total <= NEW_MAX_VISITS and last_attended >= recent):
        return NinjaEngagement.NEW
    if attended_window == 0:
        return NinjaEngagement.LAPSED
    if missed >= AT_RISK_MISSED:
        return NinjaEngagement.AT_RISK
    if attended_window >= REGULAR_MIN_VISITS and rate >= REGULAR_MIN_RATE:
        return NinjaEngagement.REGULAR
    return NinjaEngagement.OCCASIONAL


def _metrics(ninja, dojo, sessions, visits, no_shows, now, overall):
    """Window figures for one ninja at one dojo. `visits` maps event id to
    the events the ninja came to (anywhere). For the overall row, `dojo` is
    the main dojo and a visit anywhere counts: sessions they came to at
    another dojo count as offered, and a visit anywhere ends a run of
    missed sessions."""
    window_start = now - timedelta(days=WINDOW_DAYS)
    history_start = now - timedelta(days=HISTORY_DAYS)
    aimed = [s for s in sessions.get(dojo.pk, []) if s.start_time >= history_start and is_aimed_at(ninja, s)] \
        if dojo is not None else []
    offered = {s.pk for s in aimed if s.start_time >= window_start}
    counted = {pk for pk, event in visits.items() if overall or event.dojo_id == dojo.pk}
    recent_visits = {pk for pk in counted if visits[pk].start_time >= window_start}
    if overall:
        offered |= recent_visits
    attended_window = len(offered & recent_visits)
    last_visit = max((visits[pk].start_time for pk in counted), default=None)
    missed = 0
    for session in sorted(aimed, key=lambda s: s.start_time, reverse=True):
        if session.pk in counted or (last_visit is not None and session.start_time <= last_visit):
            break
        missed += 1
    no_show_since = now - timedelta(days=NO_SHOW_DAYS)
    return {
        "offered_180d": len(offered),
        "attended_180d": attended_window,
        "attendance_rate": min(1.0, attended_window / len(offered)) if offered else 0.0,
        "missed_in_a_row": missed,
        "no_shows_90d": sum(1 for s in no_shows if (overall or s.dojo_id == dojo.pk) and s.start_time >= no_show_since),
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
        ninja=ninja, dojo=None if overall else dojo, main_dojo=main,
        stage=stage(age=age, dojo_max_age=measured_at.max_age if measured_at else None, attended_total=len(days),
                    first_attended=first, last_attended=last, attended_window=metrics["attended_180d"],
                    rate=metrics["attendance_rate"], missed=metrics["missed_in_a_row"], today=today),
        first_attended=first, last_attended=last, attended_total=len(days),
        has_upcoming=bool(upcoming) if overall else dojo.pk in upcoming,
        from_marked_attendance=all(marked for _event, marked in counted.values()),
        computed_on=today, **metrics,
    )


def rebuild(today=None):
    """Recompute every NinjaEngagement row. Returns how many rows it wrote."""
    now = timezone.now()
    today = today or timezone.localdate()
    history_start = now - timedelta(days=HISTORY_DAYS)

    sessions = defaultdict(list)
    for event in Event.objects.exclude(status=Event.DRAFT).filter(start_time__lte=now, start_time__gte=history_start):
        sessions[event.dojo_id].append(event)
    marked_events = set(Registration.objects.filter(attended__isnull=False).values_list("event_id", flat=True))

    came = defaultdict(dict)       # ninja_id -> {event_id: (event, marked)}
    no_shows = defaultdict(list)   # ninja_id -> [event]
    upcoming = defaultdict(set)    # ninja_id -> {dojo_id}
    for registration in Registration.objects.select_related("event__dojo").exclude(event__status=Event.DRAFT):
        event = registration.event
        if event.start_time > now:
            if not registration.waiting_list:
                upcoming[registration.ninja_id].add(event.dojo_id)
        elif registration.attended is True:
            came[registration.ninja_id][event.pk] = (event, True)
        elif registration.attended is None and not registration.waiting_list and event.pk not in marked_events:
            came[registration.ninja_id][event.pk] = (event, False)
        elif registration.attended is False:
            no_shows[registration.ninja_id].append(event)

    rows = []
    for ninja in Ninja.objects.select_related("home_dojo"):
        visits = came.get(ninja.pk, {})
        recent = [event for event, _marked in visits.values() if event.start_time >= history_start]
        dojos = {event.dojo_id: event.dojo for event in recent}
        busiest = Counter(event.dojo_id for event in recent).most_common(1)
        main = ninja.home_dojo or (dojos[busiest[0][0]] if busiest else None)
        if main is None and visits:
            main = max(visits.values(), key=lambda v: v[0].start_time)[0].dojo
        if main is not None:
            dojos.setdefault(main.pk, main)
        shared = {"visits": visits, "sessions": sessions, "no_shows": no_shows.get(ninja.pk, []),
                  "upcoming": upcoming.get(ninja.pk, set()), "today": today, "now": now}
        rows.append(_row(ninja, None, main, True, **shared))
        rows.extend(_row(ninja, dojo, main, False, **shared) for dojo in dojos.values())

    with transaction.atomic():
        NinjaEngagement.objects.all().delete()
        NinjaEngagement.objects.bulk_create(rows, batch_size=500)
    return len(rows)
