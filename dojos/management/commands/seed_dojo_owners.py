import random

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from accounts.models import DojoOwner
from dojos.models import Dojo

FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Sophie", "Lucas", "Mila", "Finn",
    "Lotte", "Milan", "Fien", "Arthur", "Marie", "Louis", "Anna", "Jules",
]
LAST_NAMES = [
    "Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes",
    "Goossens", "Wouters", "De Smet", "Dubois", "Lambert", "Simon", "Michel",
]

DEMO_PASSWORD = "coderdojo-demo-2026"


class Command(BaseCommand):
    help = "Seed a demo DojoOwner login account for every Dojo that doesn't have one yet."

    def handle(self, *args, **options):
        rng = random.Random(1)
        created = 0
        skipped = Dojo.objects.exclude(owner=None).count()

        for dojo in Dojo.objects.filter(owner=None):
            slug = slugify(dojo.name) or f"dojo-{dojo.id}"
            username = f"owner-{dojo.id}-{slug}"[:150]
            owner = DojoOwner(
                username=username,
                email=f"{slug}@coderdojo-demo.example",
                first_name=rng.choice(FIRST_NAMES),
                last_name=rng.choice(LAST_NAMES),
            )
            owner.set_password(DEMO_PASSWORD)
            owner.save()

            dojo.owner = owner
            dojo.save(update_fields=["owner"])
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. created={created} skipped={skipped} (already had an owner). "
            f"Demo password for every seeded owner: {DEMO_PASSWORD}"
        ))
