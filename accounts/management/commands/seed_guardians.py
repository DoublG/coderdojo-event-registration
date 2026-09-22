import random

from django.core.management.base import BaseCommand

from accounts.models import ChildAccount, Guardian, Participant

GUARDIAN_FIRST_NAMES = [
    "Ellen", "Tom", "Sarah", "Bram", "Nathalie", "Wouter", "Julie", "Kevin",
    "An", "Stijn", "Karen", "Dries", "Isabelle", "Pieter", "Veerle", "Bart",
]
GUARDIAN_LAST_NAMES = [
    "Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes",
    "Goossens", "Wouters", "De Smet", "Dubois", "Lambert", "Simon", "Michel",
]
CHILD_FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Sophie", "Lucas", "Mila", "Finn",
    "Lotte", "Milan", "Fien", "Arthur", "Marie", "Louis", "Anna", "Jules",
]

NUM_GUARDIANS = 40
CHILD_LOGIN_PROBABILITY = 0.5
DEMO_PASSWORD = "coderdojo-demo-2026"


class Command(BaseCommand):
    help = (
        f"Seed {NUM_GUARDIANS} demo Guardian accounts, each with 1-3 children "
        "(Participants). About half the children get their own optional "
        "login (ChildAccount), simulating a guardian opting them in."
    )

    def handle(self, *args, **options):
        rng = random.Random(7)
        guardians_created = children_created = child_logins_created = 0

        for i in range(1, NUM_GUARDIANS + 1):
            username = f"guardian-{i}"
            if Guardian.objects.filter(username=username).exists():
                continue

            last_name = rng.choice(GUARDIAN_LAST_NAMES)
            guardian = Guardian(
                username=username,
                first_name=rng.choice(GUARDIAN_FIRST_NAMES),
                last_name=last_name,
                email=f"{username}@coderdojo-demo.example",
            )
            guardian.set_password(DEMO_PASSWORD)
            guardian.save()
            guardians_created += 1

            for child_index in range(1, rng.randint(1, 3) + 1):
                child_first_name = rng.choice(CHILD_FIRST_NAMES)
                account = None
                if rng.random() < CHILD_LOGIN_PROBABILITY:
                    account = ChildAccount(
                        username=f"{username}-child-{child_index}",
                        first_name=child_first_name,
                    )
                    account.set_password(DEMO_PASSWORD)
                    account.save()
                    child_logins_created += 1

                Participant.objects.create(
                    name=f"{child_first_name} {last_name}",
                    guardian=guardian,
                    account=account,
                )
                children_created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. guardians={guardians_created} children={children_created} "
            f"child_logins={child_logins_created}. Demo password for every seeded account: {DEMO_PASSWORD}"
        ))
