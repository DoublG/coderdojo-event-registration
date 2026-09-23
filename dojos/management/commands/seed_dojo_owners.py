import random

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from accounts.models import DojoOwner
from accounts.seed_credentials import CREDENTIALS_FILE, generate_password, write_credentials
from dojos.models import Dojo

FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Sophie", "Lucas", "Mila", "Finn",
    "Lotte", "Milan", "Fien", "Arthur", "Marie", "Louis", "Anna", "Jules",
]
LAST_NAMES = [
    "Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes",
    "Goossens", "Wouters", "De Smet", "Dubois", "Lambert", "Simon", "Michel",
]


class Command(BaseCommand):
    help = "Seed a demo DojoOwner login account for every Dojo that doesn't have one yet."

    def handle(self, *args, **options):
        rng = random.Random(1)
        created = 0
        skipped = Dojo.objects.exclude(owner=None).count()
        credential_rows = []

        for dojo in Dojo.objects.filter(owner=None):
            slug = slugify(dojo.name) or f"dojo-{dojo.id}"
            username = f"owner-{dojo.id}-{slug}"[:150]
            email = f"{slug}@coderdojo-demo.example"
            password = generate_password()
            owner = DojoOwner(
                username=username,
                email=email,
                first_name=rng.choice(FIRST_NAMES),
                last_name=rng.choice(LAST_NAMES),
            )
            owner.set_password(password)
            owner.save()

            dojo.owner = owner
            dojo.save(update_fields=["owner"])
            created += 1
            credential_rows.append((username, email, password))

        if credential_rows:
            write_credentials("dojo_owner", credential_rows)

        self.stdout.write(self.style.SUCCESS(
            f"Done. created={created} skipped={skipped} (already had an owner). "
            f"Credentials for newly seeded owners written to {CREDENTIALS_FILE}"
        ))
