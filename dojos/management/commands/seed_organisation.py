import random
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.seed_credentials import CREDENTIALS_FILE, generate_password, write_credentials
from applications.models import Application
from applications.seeding import approve_for_seeding
from content.models import Promotion
from core.image_library import use_library_image
from dojos.models import Dojo, DojoMembership
from events.models import Event

ORGANISATION_NAME = "CoderDojo Belgium"
CHAMPION_USERNAME = "organisation-champion"

# (name, weeks from today to the Saturday it's on, start, end, fields, banner)
EVENTS = [
    ("CoderDojo Girlz: Build your first website", 3, time(13, 30), time(16, 30), {
        "audience": Event.GIRLS, "places": 30, "venue_name": "De Krook, Ghent", "min_age": 8, "max_age": 16,
        "description": "An afternoon for girls who want to try coding: build and publish your own web page, "
                       "with mentors on hand the whole time. No experience needed.",
    }, "build-code.svg"),
    ("Coolest Projects Belgium", 9, time(10, 0), time(17, 0), {
        "places": 0, "venue_name": "Brussels Expo", "min_age": 7, "max_age": 18,
        "external_registration_url": "https://coolestprojects.be/",
        "description": "The yearly showcase where young makers show what they built: games, websites, robots, "
                       "apps and more. Registration and project submission happen on the Coolest Projects website.",
    }, "project-time.svg"),
]

# (event name, placement, rank, text)
PROMOTIONS = [
    ("Coolest Projects Belgium", Promotion.HOMEPAGE_HERO, 0, "Show the world what you made. Sign up your project now!"),
    ("Coolest Projects Belgium", Promotion.EVENT_LIST_TOP, 0, ""),
    ("CoderDojo Girlz: Build your first website", Promotion.UPCOMING_FIRST, 0, ""),
    ("CoderDojo Girlz: Build your first website", Promotion.DOJO_FINDER_BANNER, 0,
     "Not near a dojo? Join our girls' afternoon in Ghent."),
]


def next_saturday_in(weeks, today):
    saturday = today + timedelta(days=(5 - today.weekday()) % 7)
    return saturday + timedelta(weeks=weeks)


class Command(BaseCommand):
    help = (
        f"Seed the organisation dojo “{ORGANISATION_NAME}” (Dojo.kind=organisation, DATA_MODEL.md §12) with an "
        "approved champion, a CoderDojo Girlz session and Coolest Projects (registers externally), and example "
        "promotions for all four placements. Rerun-safe: only creates what's missing."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random("seed-organisation")
        dojo, dojo_created = Dojo.objects.get_or_create(
            name=ORGANISATION_NAME, kind=Dojo.ORGANISATION,
            defaults={"status": Dojo.ACTIVE, "email": "info@coderdojo-demo.example", "languages": ["nl-be", "fr-be", "en-us"],
                      "tagline": "The organisation behind CoderDojo in Belgium."},
        )

        champion = User.objects.filter(username=CHAMPION_USERNAME).first()
        if champion is None:
            password = generate_password()
            champion = User(username=CHAMPION_USERNAME, email="organisation@coderdojo-demo.example",
                            first_name="Lien", last_name="Vermeulen")
            champion.set_password(password)
            champion.save()
            write_credentials("organisation_champion", [(champion.username, champion.email, password)])
            self.stdout.write(f"Created {CHAMPION_USERNAME}; credentials in {CREDENTIALS_FILE}")
        approve_for_seeding(champion, Application.CHAMPION, rng, area=ORGANISATION_NAME)
        membership, _ = DojoMembership.objects.get_or_create(
            dojo=dojo, user=champion,
            defaults={"role": DojoMembership.CHAMPION, "status": DojoMembership.ACTIVE, "joined_at": timezone.now()},
        )

        today = timezone.localdate()
        events = {}
        for name, weeks, start, end, fields, banner in EVENTS:
            day = next_saturday_in(weeks, today)
            event, created = Event.objects.get_or_create(
                dojo=dojo, name=name,
                defaults={
                    "status": Event.OPEN,
                    "start_time": timezone.make_aware(datetime.combine(day, start)),
                    "end_time": timezone.make_aware(datetime.combine(day, end)),
                    # Demo data, not news (see seed_events).
                    "announced_at": timezone.now(),
                    **fields,
                },
            )
            if created:
                use_library_image(event, "image", "events", banner, save=True)
                event.team.set([membership])
            events[name] = event

        promotions = 0
        for event_name, placement, rank, text in PROMOTIONS:
            _, created = Promotion.objects.get_or_create(
                event=events[event_name], placement=placement, defaults={"rank": rank, "text": text},
            )
            promotions += created

        self.stdout.write(self.style.SUCCESS(
            f"Done. {ORGANISATION_NAME} {'created' if dojo_created else 'already there'}, "
            f"events={len(events)}, new promotions={promotions}."
        ))
