import random

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from django.utils import timezone

from accounts.models import DojoOwner
from accounts.seed_credentials import CREDENTIALS_FILE, generate_password, write_credentials
from dojos.models import Dojo, DojoMembership

FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Sophie", "Lucas", "Mila", "Finn",
    "Lotte", "Milan", "Fien", "Arthur", "Marie", "Louis", "Anna", "Jules",
]
LAST_NAMES = [
    "Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes",
    "Goossens", "Wouters", "De Smet", "Dubois", "Lambert", "Simon", "Michel",
]


class Command(BaseCommand):
    help = (
        "Seed a demo champion (the dojo's owner) for every dojo that doesn't have "
        "one yet: a DojoOwner login plus an active champion membership. Reuses an "
        "existing owner-<id>-<slug> login if there is one."
    )

    def handle(self, *args, **options):
        rng = random.Random(1)
        created = reused = 0
        skipped = Dojo.objects.filter(
            memberships__role=DojoMembership.CHAMPION, memberships__status=DojoMembership.ACTIVE,
        ).distinct().count()
        credential_rows = []

        for dojo in Dojo.objects.exclude(
            memberships__role=DojoMembership.CHAMPION, memberships__status=DojoMembership.ACTIVE,
        ):
            slug = slugify(dojo.name) or f"dojo-{dojo.id}"
            username = f"owner-{dojo.id}-{slug}"[:150]
            owner = DojoOwner.objects.filter(username=username).first()
            if owner is None:
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
                created += 1
                credential_rows.append((username, email, password))
            else:
                reused += 1

            DojoMembership.objects.update_or_create(
                dojo=dojo, user=owner,
                defaults={
                    "role": DojoMembership.CHAMPION,
                    "status": DojoMembership.ACTIVE,
                    "joined_at": timezone.now().replace(year=rng.randint(2018, 2023)),
                },
            )

        if credential_rows:
            write_credentials("dojo_owner", credential_rows)

        self.stdout.write(self.style.SUCCESS(
            f"Done. created={created} reused={reused} skipped={skipped} (already had a champion). "
            f"Credentials for newly seeded owners written to {CREDENTIALS_FILE}"
        ))
