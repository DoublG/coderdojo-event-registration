import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from content.models import Announcement
from dojos.models import Dojo

# Short, dated notes a dojo's team posts on its public page ("From this
# dojo", see dojos/dojo_detail.html) — a bulletin board, not a blog, and
# never a second FAQ or schedule. {dojo} is filled in per dojo.
ANNOUNCEMENTS = [
    "We've moved to a bigger room from next month — same time, same entrance, just more elbow room.",
    "Looking for one more volunteer mentor comfortable with Python for alternate sessions. Get in touch if that's you!",
    "Thanks to a local sponsor we now have six loaner laptops. No laptop at home? Just let us know when you sign up.",
    "Our micro:bits have arrived! Ninjas who want to try physical computing can ask a mentor on the day.",
    "Three of our ninjas are presenting their projects at Coolest Projects this year. Come and cheer them on!",
    "Reminder: please bring a charger for your laptop, the room has plenty of sockets.",
    "The entrance on the side of the building is closed for works; use the main door this month.",
    "{dojo} is taking a short summer break. Sessions start again in September.",
    "New this term: a beginners' corner for first-timers, with a mentor dedicated to getting you started.",
    "Parents are welcome to stay and watch, there's coffee in the hall.",
    "We're trying out a web development track. Ninjas who finished a Scratch project can give it a go.",
    "Big thank you to everyone who came to our open day. Over twenty new ninjas signed up!",
    "Our Raspberry Pi kits are back from repair, so the hardware table is open again.",
    "Mentors: team meeting after next session to plan the rest of the season.",
]


class Command(BaseCommand):
    help = "Seed a few random updates ('From this dojo') for dojos that have none yet."

    def handle(self, *args, **options):
        today = timezone.localdate()
        created = 0
        for dojo in Dojo.objects.public().filter(announcements__isnull=True):
            # Own RNG per dojo (rerun-safe: only dojos without updates get any).
            rng = random.Random(f"announcements-{dojo.id}")
            for text in rng.sample(ANNOUNCEMENTS, rng.randint(0, 4)):
                Announcement.objects.create(
                    dojo=dojo,
                    date=today - timedelta(days=rng.randint(0, 120)),
                    text=text.format(dojo=dojo.name),
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Done. created={created}"))
