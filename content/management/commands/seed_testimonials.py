from django.core.management.base import BaseCommand

from content.models import Testimonial
from core.audit import without_audit_log

# Site-wide quotes (Testimonial.dojo=None) — the homepage picks one of
# these at random on every load (see core.views.home).
TESTIMONIALS = [
    {
        "quote": "My daughter built her first game in one Saturday morning and hasn't stopped talking about it since.",
        "author": "Sofie",
        "role": "parent",
    },
    {
        "quote": "I never thought I'd say this, but my son asks to wake up early on dojo Saturdays.",
        "author": "Kevin",
        "role": "parent",
    },
    {
        "quote": "I made a website with my own name on it. My friends at school didn't believe me until I showed them.",
        "author": "Amber (11)",
        "role": "ninja",
    },
    {
        "quote": "Watching a room of eight-year-olds debug their own Scratch project, patiently, without giving up — that's why I keep coming back to mentor.",
        "author": "Dries",
        "role": "volunteer mentor",
    },
    {
        "quote": "It's free, it's local, and the mentors clearly love doing this. What more could you ask for on a Saturday morning?",
        "author": "Isabelle",
        "role": "parent",
    },
    {
        "quote": "We flashed our first program onto a micro:bit and my daughter wore it around her neck for a week.",
        "author": "Bart",
        "role": "parent",
    },
    {
        "quote": "I started as a ninja here at 10. I'm 17 now and mentoring the next group — this place is why I'm studying computer science.",
        "author": "Milan (17)",
        "role": "ninja mentor",
    },
]


class Command(BaseCommand):
    help = "Seed a handful of site-wide testimonials the homepage picks from at random."

    @without_audit_log
    def handle(self, *args, **options):
        created = 0
        for t in TESTIMONIALS:
            _, was_created = Testimonial.objects.get_or_create(
                dojo=None, author=t["author"], quote=t["quote"],
                defaults={"role": t["role"]},
            )
            created += 1 if was_created else 0

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} testimonials."))
