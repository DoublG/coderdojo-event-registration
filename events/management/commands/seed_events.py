import itertools
import random
from calendar import monthrange
from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from dojos.models import Dojo
from events.models import Event

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

        for dojo in Dojo.objects.exclude(location=None):
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
                _, was_created = Event.objects.get_or_create(
                    dojo=dojo,
                    start_time=start_dt,
                    defaults={
                        "name": f"{dojo.name} - {event_date.strftime('%d/%m/%Y')}",
                        "end_time": end_dt,
                        "places": rng.choice(CAPACITY_CHOICES),
                        "location": dojo.location,
                        "min_age": min_age,
                        "max_age": max_age,
                    },
                )
                created += 1 if was_created else 0
                skipped += 1 if not was_created else 0

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} skipped={skipped} (already existed)."))
