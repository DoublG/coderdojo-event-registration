import itertools
import random
from calendar import monthrange
from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.audit import without_audit_log
from core.image_library import use_library_image
from dojos.models import Dojo
from events.models import Event
from events.template_images import TEMPLATE_IMAGES
from pathways.models import Pathway

SATURDAY, SUNDAY, WEDNESDAY, FRIDAY = 5, 6, 2, 4

WEEKEND_MORNING = (time(9, 30), time(11, 0))
WEEKEND_AFTERNOON = (time(13, 30), time(16, 0))
WEDNESDAY_SLOT = (time(13, 0), time(18, 0))
FRIDAY_SLOT = (time(18, 0), time(20, 30))

EVENTS_PER_DOJO = 3
CAPACITY_CHOICES = [15, 20, 24, 30]
# Most sessions are open to the dojo's full age range; a minority run a
# narrower specialised track (younger Scratch-only, or an older/advanced
# group) — weighted so "all ages" is the common case.
AGE_RANGE_CHOICES = [(7, 18), (7, 18), (7, 18), (7, 10), (10, 14), (13, 18)]

# Most chapters run a monthly weekend workshop; a minority instead run a
# weekly Wednesday or Friday session.
PATTERN_WEIGHTS = {"weekend": 60, "wednesday": 20, "friday": 20}

# The event's own name — not the dojo's name and not the date, both of
# which are already shown alongside it (see events/partials/_event_row.html
# and event_detail.html), so baking either into the name would just repeat
# it. Derived from events.template_images.TEMPLATE_IMAGES (the same list
# the dojo owner's own "choose from templates" banner picker uses) so the
# names and their banner images can't drift apart.
SESSION_NAMES = [label for _filename, label in TEMPLATE_IMAGES]

# Share of upcoming seeded sessions labelled as girls' sessions.
GIRLS_SESSION_SHARE = 0.06

# A minority of weekend dojos run a second track the same day — a later
# session, or (see PARALLEL_TRACK_SHARE) a second group meeting at the very
# same time — so a fresh seed has a real example of two same-dojo sessions
# on one day (the events list's same-dojo grouping indicator,
# events.views._cluster_by_dojo_per_day), not just single sessions spread
# one per day.
SAME_DAY_SECOND_TRACK_SHARE = 0.12
# Of those, the share that run at the very same time as a genuinely separate
# track rather than later that day — e.g. a Scratch group and a Python group
# meeting in parallel, tagged with their own pathway when both are seeded.
PARALLEL_TRACK_SHARE = 0.5

# One banner image per session name, shown on the homepage's "Upcoming
# sessions" card — see events/templates/events/partials/_upcoming_session_card.html.
SESSION_IMAGES = {label: filename for filename, label in TEMPLATE_IMAGES}


def description_for(session_name):
    """A single Markdown-formatted blurb covering both what the session is
    and what to bring — Event has just the one free-text field, with
    Markdown headings (see core.templatetags.markdown_extras) doing the
    work a separate what_to_bring field used to."""
    return (
        f"**{session_name}** is a hands-on, beginner-friendly session. What you'll do:\n\n"
        "- Pick a project and start building\n"
        "- Get 1:1 help from a mentor whenever you're stuck\n"
        "- Show off what you made at the end (totally optional)\n\n"
        "### Bring with you\n\n"
        "- A laptop, if you have one (we have a few spares to lend out)\n"
        "- A water bottle and a snack\n\n"
        "### Not required\n\n"
        "No experience, no accounts to set up in advance — we'll get you going on the day."
    )


def assign_session_image(event, session_name):
    use_library_image(event, "image", "events", SESSION_IMAGES[session_name], save=True)


def nth_weekday_dates(start_date, weekday, n_occurrence):
    """The n_occurrence-th `weekday` of each month, from start_date's month
    onward, skipping any date before start_date."""
    year, month = start_date.year, start_date.month
    while True:
        days_in_month = monthrange(year, month)[1]
        matches = [
            date(year, month, day)
            for day in range(1, days_in_month + 1)
            if date(year, month, day).weekday() == weekday
        ]
        if n_occurrence <= len(matches):
            candidate = matches[n_occurrence - 1]
            if candidate >= start_date:
                yield candidate
        month += 1
        if month > 12:
            month = 1
            year += 1


def weekly_dates(start_date, weekday):
    current = start_date + timedelta(days=(weekday - start_date.weekday()) % 7)
    while True:
        yield current
        current += timedelta(days=7)


def create_session(dojo, start_dt, end_dt, name, min_age, max_age, capacity, pathways, created_ids):
    """get_or_create one Event plus its banner, pathways and team — shared by
    a dojo's regular sessions and its occasional same-day second track."""
    event, was_created = Event.objects.get_or_create(
        dojo=dojo,
        start_time=start_dt,
        defaults={
            "name": name,
            "status": Event.OPEN,
            "end_time": end_dt,
            "places": capacity,
            "location": dojo.location,
            "min_age": min_age,
            "max_age": max_age,
            "description": description_for(name),
        },
    )
    if was_created:
        created_ids.append(event.id)
        assign_session_image(event, name)
        event.pathways.set(pathways)
        assign_event_team(event)
    return was_created


def assign_event_team(event, max_mentors=2):
    """Who runs the session: the dojo's champion plus a few of its active
    mentors. Its own RNG per event, so it doesn't shift any other choices."""
    team_rng = random.Random(f"event-team-{event.id}")
    managers = list(event.dojo.memberships.managers().order_by("id"))
    champion = [m for m in managers if m.role == m.CHAMPION]
    mentors = [m for m in managers if m.role != m.CHAMPION]
    event.team.set(champion + team_rng.sample(mentors, k=min(len(mentors), team_rng.randint(0, max_mentors))))


class Command(BaseCommand):
    help = (
        f"Seed {EVENTS_PER_DOJO} demo upcoming Events for every Dojo that has a "
        "location: most get a monthly Saturday/Sunday morning-or-afternoon "
        "workshop, some get a weekly Wednesday or Friday session instead."
    )

    @without_audit_log
    def handle(self, *args, **options):
        rng = random.Random(42)
        today = timezone.localdate()
        created, skipped = 0, 0
        created_ids = []

        all_pathways = list(Pathway.objects.order_by("id"))
        scratch_pathway = next((p for p in all_pathways if p.name == "Scratch"), None)
        python_pathway = next((p for p in all_pathways if p.name == "Python"), None)

        for dojo in Dojo.objects.exclude(location=None):
            # The pathways this dojo provides (a few of them), which its new
            # sessions pre-select. Own RNG: drawing from `rng` only when unset
            # would shift every later choice on a rerun (duplicate events).
            if all_pathways and not dojo.pathways.exists():
                pathway_rng = random.Random(f"dojo-pathways-{dojo.id}")
                dojo.pathways.set(
                    pathway_rng.sample(all_pathways, k=min(len(all_pathways), pathway_rng.randint(1, 3)))
                )
            dojo_pathways = list(dojo.pathways.all())
            pattern = rng.choices(list(PATTERN_WEIGHTS), weights=list(PATTERN_WEIGHTS.values()))[0]

            if pattern == "weekend":
                weekday = rng.choice([SATURDAY, SUNDAY])
                start_t, end_t = rng.choice([WEEKEND_MORNING, WEEKEND_AFTERNOON])
                nth_occurrence = rng.randint(1, 3)
                dates = nth_weekday_dates(today, weekday, nth_occurrence)
            elif pattern == "wednesday":
                start_t, end_t = WEDNESDAY_SLOT
                dates = weekly_dates(today, WEDNESDAY)
            else:
                start_t, end_t = FRIDAY_SLOT
                dates = weekly_dates(today, FRIDAY)

            # Own RNG: drawing only when a dojo actually qualifies (weekend
            # pattern) would shift every later dojo's choices on a rerun.
            second_track_rng = random.Random(f"dojo-second-track-{dojo.id}")
            runs_second_track = pattern == "weekend" and second_track_rng.random() < SAME_DAY_SECOND_TRACK_SHARE
            runs_parallel_track = runs_second_track and second_track_rng.random() < PARALLEL_TRACK_SHARE

            for index, event_date in enumerate(itertools.islice(dates, EVENTS_PER_DOJO)):
                start_dt = timezone.make_aware(datetime.combine(event_date, start_t))
                end_dt = timezone.make_aware(datetime.combine(event_date, end_t))
                min_age, max_age = rng.choice(AGE_RANGE_CHOICES)
                session_name = rng.choice(SESSION_NAMES)
                capacity = rng.choice(CAPACITY_CHOICES)
                # A draft/dormant/archived dojo has no upcoming sessions (the
                # lifecycle rules); the draws above still happen so the other
                # dojos' choices don't shift.
                if dojo.status != Dojo.ACTIVE:
                    continue
                # A parallel second track tags this one Scratch (and the
                # other Python below) instead of the dojo's usual mixed
                # pathways, so the two read as genuinely separate groups.
                primary_pathways = dojo_pathways
                if runs_parallel_track and index == 0 and scratch_pathway and python_pathway:
                    primary_pathways = [scratch_pathway]
                was_created = create_session(
                    dojo, start_dt, end_dt, session_name, min_age, max_age, capacity, primary_pathways, created_ids
                )
                created += 1 if was_created else 0
                skipped += 1 if not was_created else 0

                if runs_second_track and index == 0:
                    if runs_parallel_track:
                        # The very same time, not just the same day — two
                        # separate groups meeting in parallel (e.g. Scratch
                        # and Python). Offset by a second so it gets its own
                        # row (create_session's natural key is dojo+start
                        # time) without changing what visitors see: the
                        # "H:i" display drops seconds, so both rows still
                        # show the identical time.
                        other_start_dt = start_dt + timedelta(seconds=1)
                        other_end_dt = end_dt
                    else:
                        # The other time slot, same day: a later second
                        # track rather than a second date, so this dojo's
                        # two sessions sit next to each other on the list.
                        other_t = WEEKEND_AFTERNOON if (start_t, end_t) == WEEKEND_MORNING else WEEKEND_MORNING
                        other_start_dt = timezone.make_aware(datetime.combine(event_date, other_t[0]))
                        other_end_dt = timezone.make_aware(datetime.combine(event_date, other_t[1]))
                    other_name = second_track_rng.choice([n for n in SESSION_NAMES if n != session_name])
                    other_min_age, other_max_age = second_track_rng.choice(AGE_RANGE_CHOICES)
                    other_capacity = second_track_rng.choice(CAPACITY_CHOICES)
                    other_pathways = dojo_pathways
                    if runs_parallel_track and scratch_pathway and python_pathway:
                        other_pathways = [python_pathway]
                    was_created = create_session(
                        dojo,
                        other_start_dt,
                        other_end_dt,
                        other_name,
                        other_min_age,
                        other_max_age,
                        other_capacity,
                        other_pathways,
                        created_ids,
                    )
                    created += 1 if was_created else 0
                    skipped += 1 if not was_created else 0

        # Seeded sessions are demo data, not news: mark them announced so the
        # daily "new sessions" mail doesn't write to every seeded family.
        Event.objects.filter(pk__in=created_ids, announced_at=None).update(announced_at=timezone.now())

        # Some upcoming sessions are CoderDojo Girlz sessions (Event.audience,
        # a label only). Per-event RNG, so the pick is the same on every run
        # and doesn't shift the shared stream; flipped once, never back.
        for event in Event.objects.filter(status=Event.OPEN, audience=Event.EVERYONE, start_time__gte=timezone.now()):
            if random.Random(f"event-audience-{event.id}").random() < GIRLS_SESSION_SHARE:
                event.audience = Event.GIRLS
                event.name = f"CoderDojo Girlz: {event.name}"
                event.save(update_fields=["audience", "name"])

        # Backfill: events seeded before Event.image existed have no
        # banner yet — give them one based on their (already-set) name.
        for event in Event.objects.all():
            if not event.image and event.name in SESSION_IMAGES:
                assign_session_image(event, event.name)

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} skipped={skipped} (already existed)."))
