from django.core.management.base import BaseCommand

from content.models import FAQ
from dojos.models import Dojo
from events.models import Event

# Site-wide questions (FAQ.dojo/event/pathway all None) — these were
# previously hardcoded straight into core/templates/core/home.html; moving
# them into the DB is what lets the homepage (and FAQ.objects.for_dojo())
# show them alongside any dojo-specific ones. See content.models.FAQQuerySet.
GLOBAL_FAQS = [
    {
        "question": "Is it really free?",
        "answer": "Yes — every Dojo session is free, run entirely by volunteers.",
        "order": 0,
    },
    {
        "question": "Does my child need coding experience?",
        "answer": "No experience needed — we group by age and skill on the day, not in advance.",
        "order": 1,
    },
    {
        "question": "Do parents need to stay?",
        "answer": "Under-12s need an adult on site; older kids can be dropped off.",
        "order": 2,
    },
]

# A couple of dojo-specific examples, just to exercise FAQ.objects.for_dojo()
# — real chapters would add their own through the admin.
DOJO_FAQS = [
    {"question": "Is there parking nearby?", "answer": "Yes, free parking is available right outside the venue."},
    {"question": "Is the venue wheelchair accessible?", "answer": "Yes, there's step-free access and an accessible toilet."},
]

# A couple of session-specific examples, to exercise FAQ.objects.for_event().
EVENT_FAQS = [
    {"question": "Is there a waitlist if it's full?", "answer": "Yes — sign up anyway and we'll email you if a spot opens up."},
    {"question": "Can I drop in late?", "answer": "Yes, just check in at the door — you won't miss much."},
]


class Command(BaseCommand):
    help = "Seed the site-wide FAQs shown on the homepage, plus a couple of dojo- and event-specific examples."

    def handle(self, *args, **options):
        created = 0

        for faq in GLOBAL_FAQS:
            _, was_created = FAQ.objects.get_or_create(
                dojo=None, event=None, pathway=None, question=faq["question"],
                defaults={"answer": faq["answer"], "order": faq["order"]},
            )
            created += 1 if was_created else 0

        for dojo in Dojo.objects.all()[:2]:
            for i, faq in enumerate(DOJO_FAQS):
                _, was_created = FAQ.objects.get_or_create(
                    dojo=dojo, event=None, pathway=None, question=faq["question"],
                    defaults={"answer": faq["answer"], "order": i},
                )
                created += 1 if was_created else 0

        for event in Event.objects.all()[:2]:
            for i, faq in enumerate(EVENT_FAQS):
                _, was_created = FAQ.objects.get_or_create(
                    dojo=None, event=event, pathway=None, question=faq["question"],
                    defaults={"answer": faq["answer"], "order": i},
                )
                created += 1 if was_created else 0

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} FAQs."))
