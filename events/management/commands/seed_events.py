import itertools
import random
from calendar import monthrange
from datetime import date, datetime, time, timedelta

from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils import timezone

from dojos.models import Dojo
from events.models import Event
from events.template_images import TEMPLATE_IMAGES, TEMPLATE_IMAGES_DIR
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
    image_path = TEMPLATE_IMAGES_DIR / SESSION_IMAGES[session_name]
    with open(image_path, "rb") as f:
        event.image.save(image_path.name, File(f), save=True)


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


class Command(BaseCommand):
    help = (
        f"Seed {EVENTS_PER_DOJO} demo upcoming Events for every Dojo that has a "
        "location: most get a monthly Saturday/Sunday morning-or-afternoon "
        "workshop, some get a weekly Wednesday or Friday session instead."
    )

    def handle(self, *args, **options):
        rng = random.Random(42)
        today = timezone.localdate()
        created, skipped = 0, 0

        all_pathways = list(Pathway.objects.order_by("id"))
        for dojo in Dojo.objects.exclude(location=None):
            # The pathways this dojo provides (a few of them), which its new
            # sessions pre-select.
            if all_pathways and not dojo.pathways.exists():
                dojo.pathways.set(rng.sample(all_pathways, k=min(len(all_pathways), rng.randint(1, 3))))
            dojo_pathways = list(dojo.pathways.all())
            pattern = rng.choices(
                list(PATTERN_WEIGHTS), weights=list(PATTERN_WEIGHTS.values())
            )[0]

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

            for event_date in itertools.islice(dates, EVENTS_PER_DOJO):
                start_dt = timezone.make_aware(datetime.combine(event_date, start_t))
                end_dt = timezone.make_aware(datetime.combine(event_date, end_t))
                min_age, max_age = rng.choice(AGE_RANGE_CHOICES)
                session_name = rng.choice(SESSION_NAMES)
                event, was_created = Event.objects.get_or_create(
                    dojo=dojo,
                    start_time=start_dt,
                    defaults={
                        "name": session_name,
                        "status": Event.OPEN,
                        "end_time": end_dt,
                        "places": rng.choice(CAPACITY_CHOICES),
                        "location": dojo.location,
                        "min_age": min_age,
                        "max_age": max_age,
                        "description": description_for(session_name),
                    },
                )
                if was_created:
                    assign_session_image(event, session_name)
                    event.pathways.set(dojo_pathways)
                created += 1 if was_created else 0
                skipped += 1 if not was_created else 0

        # Backfill: events seeded before Event.image existed have no
        # banner yet — give them one based on their (already-set) name.
        for event in Event.objects.all():
            if not event.image and event.name in SESSION_IMAGES:
                assign_session_image(event, event.name)

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} skipped={skipped} (already existed)."))
