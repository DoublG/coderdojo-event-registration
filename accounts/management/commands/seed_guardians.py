import random
from datetime import timedelta
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import ChildAccount, Guardian, Participant
from accounts.seed_credentials import CREDENTIALS_FILE, generate_password, write_credentials
from dojos.models import Dojo

# Reuse the same fun alien/robot/animal avatars seeded for ninja mentors
# (dojos/seed_data/kid_avatars/) — same audience, same round .cd-mentor__avatar.
KID_AVATARS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "dojos" / "seed_data" / "kid_avatars"
)
KID_AVATAR_FILES = sorted(KID_AVATARS_DIR.glob("*.svg"))

GUARDIAN_FIRST_NAMES = [
    "Ellen", "Tom", "Sarah", "Bram", "Nathalie", "Wouter", "Julie", "Kevin",
    "An", "Stijn", "Karen", "Dries", "Isabelle", "Pieter", "Veerle", "Bart", "Thomas"
]
GUARDIAN_LAST_NAMES = [
    "Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes",
    "Goossens", "Wouters", "De Smet", "Dubois", "Lambert", "Simon", "Michel",
]
CHILD_FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Sophie", "Lucas", "Mila", "Finn", "Nina",
    "Lotte", "Milan", "Fien", "Arthur", "Marie", "Louis", "Anna", "Jules", "Mara"
]

NUM_GUARDIANS = 40
CHILD_LOGIN_PROBABILITY = 0.5


class Command(BaseCommand):
    help = (
        f"Seed {NUM_GUARDIANS} demo Guardian accounts, each with 1-3 children "
        "(Participants). About half the children get their own optional "
        "login (ChildAccount), simulating a guardian opting them in."
    )

    def handle(self, *args, **options):
        rng = random.Random(7)
        guardians_created = children_created = child_logins_created = 0
        dojos = list(Dojo.objects.exclude(location=None))
        today = timezone.localdate()
        guardian_credential_rows = []
        child_credential_rows = []

        for i in range(1, NUM_GUARDIANS + 1):
            username = f"guardian-{i}"
            if Guardian.objects.filter(username=username).exists():
                continue

            last_name = rng.choice(GUARDIAN_LAST_NAMES)
            email = f"{username}@coderdojo-demo.example"
            guardian_password = generate_password()
            guardian = Guardian(
                username=username,
                first_name=rng.choice(GUARDIAN_FIRST_NAMES),
                last_name=last_name,
                email=email,
            )
            guardian.set_password(guardian_password)
            guardian.save()
            guardians_created += 1
            guardian_credential_rows.append((username, email, guardian_password))

            for child_index in range(1, rng.randint(1, 3) + 1):
                child_first_name = rng.choice(CHILD_FIRST_NAMES)
                account = None
                if rng.random() < CHILD_LOGIN_PROBABILITY:
                    child_username = f"{username}-child-{child_index}"
                    child_password = generate_password()
                    account = ChildAccount(
                        username=child_username,
                        first_name=child_first_name,
                    )
                    account.set_password(child_password)
                    account.save()
                    child_logins_created += 1
                    child_credential_rows.append((child_username, "", child_password))

                participant = Participant.objects.create(
                    name=f"{child_first_name} {last_name}",
                    guardian=guardian,
                    account=account,
                    home_dojo=rng.choice(dojos) if dojos else None,
                    member_since=today - timedelta(days=rng.randint(30, 5 * 365)),
                )
                avatar_path = rng.choice(KID_AVATAR_FILES)
                with open(avatar_path, "rb") as f:
                    participant.photo.save(avatar_path.name, File(f), save=True)
                children_created += 1

        # Backfill: children seeded before Participant.photo/home_dojo/
        # member_since were set this way (guardians already existing skip
        # the loop above entirely, so this is the only path that reaches them).
        for participant in Participant.objects.all():
            dirty_fields = []
            if not participant.photo:
                avatar_path = rng.choice(KID_AVATAR_FILES)
                with open(avatar_path, "rb") as f:
                    participant.photo.save(avatar_path.name, File(f), save=False)
                dirty_fields.append("photo")
            if not participant.home_dojo_id and dojos:
                participant.home_dojo = rng.choice(dojos)
                dirty_fields.append("home_dojo")
            if not participant.member_since:
                participant.member_since = today - timedelta(days=rng.randint(30, 5 * 365))
                dirty_fields.append("member_since")
            if dirty_fields:
                participant.save(update_fields=dirty_fields)

        if guardian_credential_rows:
            write_credentials("guardian", guardian_credential_rows)
        if child_credential_rows:
            write_credentials("child_account", child_credential_rows)

        self.stdout.write(self.style.SUCCESS(
            f"Done. guardians={guardians_created} children={children_created} "
            f"child_logins={child_logins_created}. Credentials for newly seeded accounts "
            f"written to {CREDENTIALS_FILE}"
        ))
