"""What a dojo's dashboard shows (dojos.views.dashboard, `/dojos/<id>/dashboard/`):
what needs the team now, the next sessions, the dojo's ninjas and its year so
far. Read-only and made of a handful of aggregate queries; every part links to
the page that does the work (Team, Events, Attendance, Members). Health notes
never show here (only on the attendance list), and the engagement stages only
as counts, never per child."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext

from accounts.models import Ninja, User
from events import questions as event_questions
from events.models import Event, NinjaBelt, NinjaEngagement, Registration

from .access import DojoAccess
from .models import Dojo, DojoMembership
from .team import needs_dormancy_nudge

if TYPE_CHECKING:
    from django.db.models import QuerySet

# A draft, or a session without its team, this close is worth a warning.
SOON = timedelta(days=14)
# No session at all within this period: time to plan the next one.
PLAN_AHEAD = timedelta(days=42)
# A background check that ends within this period: getting a new extract
# takes a while (it can only be uploaded once the old check has lapsed).
CHECK_WARNING = timedelta(days=60)
# Past sessions with places still unmarked, looked for this far back.
UNMARKED_LOOKBACK = timedelta(days=90)
UNMARKED_LIMIT = 3
# The sessions in the Coming up agenda, the next one included.
AGENDA_LIMIT = 6


@dataclass
class AgendaDate:
    """One day with sessions on it (the design system's Calendar never shows
    an empty day); `selected` marks the next session's day."""

    day: date
    events: list[Event]
    selected: bool


@dataclass
class AgendaPeriod:
    """A relative bucket of days: Today, This week, Next week, Later in
    <month>, then a month name."""

    title: str
    dates: list[AgendaDate]


@dataclass
class CheckWarning:
    """A team member whose background check ends soon or has ended (then
    they've lost the admin area until a new one is validated)."""

    membership: DojoMembership
    expires_at: datetime | None
    lapsed: bool
    renewal_submitted: bool
    is_self: bool


@dataclass
class Attention:
    """The "Needs attention" list: each part empty when there's nothing to do,
    and only filled for a role that can act on it."""

    join_requests: int = 0
    unmarked_sessions: list[Event] = field(default_factory=list)
    drafts_soon: list[Event] = field(default_factory=list)
    without_team_soon: list[Event] = field(default_factory=list)
    nothing_planned: bool = False
    checks: list[CheckWarning] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(
            self.join_requests
            or self.unmarked_sessions
            or self.drafts_soon
            or self.without_team_soon
            or self.nothing_planned
            or self.checks
        )


@dataclass
class YearFigures:
    sessions: int
    ninjas: int
    turnout_percent: int | None  # None: no places marked yet this year
    belts: int


@dataclass
class Overview:
    dormancy_nudge: bool
    attention: Attention
    next_session: Event | None
    next_session_waiting: int
    next_session_answers: list[dict[str, Any]]
    agenda: list[AgendaPeriod]
    members: int
    stages: list[tuple[str, str, int]]  # (stage, label, count), in STAGE_CHOICES order
    year: YearFigures


def build(access: DojoAccess, now: datetime | None = None) -> Overview:
    dojo = access.dojo
    now = now or timezone.now()
    upcoming = list(
        Event.objects.with_confirmed_count()
        .filter(dojo=dojo, start_time__gte=now)
        .annotate(waiting_count=Count("registration", filter=Q(registration__waiting_list=True)))
        .prefetch_related("team__user")
        .order_by("start_time")[:AGENDA_LIMIT]
    )
    next_session = upcoming[0] if upcoming else None
    dormancy_nudge = needs_dormancy_nudge(dojo)
    return Overview(
        dormancy_nudge=dormancy_nudge,
        attention=_attention(access, now, dormancy_nudge),
        next_session=next_session,
        next_session_waiting=next_session.waiting_count if next_session else 0,
        next_session_answers=event_questions.totals(next_session) if next_session else [],
        agenda=agenda(upcoming, timezone.localdate(now)),
        members=Ninja.objects.filter(home_dojo=dojo).count(),
        stages=_stages(dojo),
        year=_year(dojo, now),
    )


def agenda(events: list[Event], today: date) -> list[AgendaPeriod]:
    """The sessions (in start order) as the design system's Calendar agenda:
    grouped by day, the days by period relative to `today` (Belgian time)."""
    periods: list[AgendaPeriod] = []
    selected_day = timezone.localdate(events[0].start_time) if events else None
    for event in events:
        day = timezone.localdate(event.start_time)
        title = period_title(day, today)
        if not periods or periods[-1].title != title:
            periods.append(AgendaPeriod(title=title, dates=[]))
        dates = periods[-1].dates
        if not dates or dates[-1].day != day:
            dates.append(AgendaDate(day=day, events=[], selected=day == selected_day))
        dates[-1].events.append(event)
    return periods


def period_title(day: date, today: date) -> str:
    """ "This week" runs through Sunday, "Next week" is the Monday to Sunday
    after it; further out "Later in <this month>", then the month's name
    (with its year when that isn't this year)."""
    end_of_week = today + timedelta(days=6 - today.weekday())
    if day <= today:
        return gettext("Today")
    if day <= end_of_week:
        return gettext("This week")
    if day <= end_of_week + timedelta(days=7):
        return gettext("Next week")
    if (day.year, day.month) == (today.year, today.month):
        return gettext("Later in %(month)s") % {"month": date_format(day, "F")}
    return date_format(day, "F" if day.year == today.year else "F Y")


def _attention(access: DojoAccess, now: datetime, dormancy_nudge: bool) -> Attention:
    dojo = access.dojo
    attention = Attention()
    if access.can_manage_team:
        attention.join_requests = dojo.memberships.filter(status=DojoMembership.REQUESTED).count()
    if access.can_take_attendance:
        attention.unmarked_sessions = unmarked_sessions(dojo, now)
    if access.can_manage_events:
        soon = dojo.event_set.filter(start_time__gte=now, start_time__lt=now + SOON).order_by("start_time")
        attention.drafts_soon = list(soon.filter(status=Event.DRAFT))
        attention.without_team_soon = list(soon.annotate(team_count=Count("team")).filter(team_count=0))
        attention.nothing_planned = (
            dojo.status == Dojo.ACTIVE
            and not dojo.is_organisation
            and not dormancy_nudge
            and not dojo.event_set.filter(start_time__gte=now, start_time__lt=now + PLAN_AHEAD).exists()
        )
    attention.checks = check_warnings(access, now)
    return attention


def unmarked_sessions(dojo: Dojo, now: datetime) -> list[Event]:
    """Sessions that have ended (in the last UNMARKED_LOOKBACK) with confirmed
    places nobody has marked present or absent, newest first, each with
    `unmarked_count`."""
    return list(
        dojo.event_set.filter(end_time__lt=now, end_time__gte=now - UNMARKED_LOOKBACK)
        .annotate(
            unmarked_count=Count(
                "registration",
                filter=Q(registration__waiting_list=False, registration__attended__isnull=True),
            )
        )
        .filter(unmarked_count__gt=0)
        .order_by("-start_time")[:UNMARKED_LIMIT]
    )


def check_warnings(access: DojoAccess, now: datetime) -> list[CheckWarning]:
    """Background checks that end within CHECK_WARNING or have ended. The
    champion sees every champion and mentor on the team (someone whose check
    has lapsed can't get into the admin area to see it themselves); a mentor
    only their own."""
    memberships: QuerySet[DojoMembership] = access.dojo.memberships.managers().select_related("user")
    if not access.is_champion:
        memberships = memberships.filter(pk=access.membership.pk)
    warnings = []
    for membership in memberships.order_by("user__first_name", "user__last_name"):
        user = membership.user
        expires_at = user.background_check_expires_at
        lapsed = not user.background_check_valid
        if not lapsed and expires_at is not None and expires_at > now + CHECK_WARNING:
            continue
        warnings.append(
            CheckWarning(
                membership=membership,
                expires_at=expires_at,
                lapsed=lapsed,
                renewal_submitted=user.background_check_status == User.CHECK_SUBMITTED,
                is_self=membership.user_id == access.membership.user_id,
            )
        )
    return warnings


def _stages(dojo: Dojo) -> list[tuple[str, str, int]]:
    """How the dojo's own members (home dojo) come to it, from last night's
    engagement snapshot: a count per stage, never names."""
    counts = dict(
        NinjaEngagement.objects.filter(dojo=dojo, ninja__home_dojo=dojo)
        .values_list("stage")
        .annotate(n=Count("id"))
        .values_list("stage", "n")
    )
    return [(stage, str(label), counts[stage]) for stage, label in NinjaEngagement.STAGE_CHOICES if counts.get(stage)]


def _year(dojo: Dojo, now: datetime) -> YearFigures:
    """This calendar year (Belgian time) up to now: sessions held (not drafts),
    different ninjas who came, the share of marked places that turned up, and
    the belts the team awarded."""
    start = timezone.localtime(now).replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    held = dojo.event_set.filter(start_time__gte=start, start_time__lt=now).exclude(status=Event.DRAFT)
    places = Registration.objects.filter(event__in=held, waiting_list=False).aggregate(
        present=Count("id", filter=Q(attended=True)),
        marked=Count("id", filter=Q(attended__isnull=False)),
        ninjas=Count("ninja", filter=Q(attended=True), distinct=True),
    )
    return YearFigures(
        sessions=held.count(),
        ninjas=places["ninjas"],
        turnout_percent=round(100 * places["present"] / places["marked"]) if places["marked"] else None,
        belts=NinjaBelt.objects.filter(awarded_as_membership__dojo=dojo, awarded_on__gte=start.date()).count(),
    )
