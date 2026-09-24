import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from accounts.seed_credentials import CREDENTIALS_FILE, generate_password, write_credentials
from accounts.template_avatars import TEMPLATE_KID_AVATARS
from core.image_library import use_library_image
from dojos.models import Dojo, DojoMembership

# Reuse the same fun alien/robot/animal avatars seeded for ninja mentors
# (accounts.template_avatars) — same audience, same round .cd-mentor__avatar.
KID_AVATAR_FILES = [filename for filename, _label in TEMPLATE_KID_AVATARS]

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
        f"Seed {NUM_GUARDIANS} demo parent accounts, each with 1-3 ninjas "
        "(Ninjas, linked through Guardianship). About half the ninjas get "
        "their own optional login (an account of type ninja), simulating a "
        "parent opting them in."
    )

    def handle(self, *args, **options):
        rng = random.Random(7)
        guardians_created = children_created = child_logins_created = 0
        dojos = list(Dojo.objects.public().exclude(location=None))
        today = timezone.localdate()
        guardian_credential_rows = []
        child_credential_rows = []

        for i in range(1, NUM_GUARDIANS + 1):
            username = f"guardian-{i}"
            if User.objects.filter(username=username).exists():
                continue

            last_name = rng.choice(GUARDIAN_LAST_NAMES)
            email = f"{username}@coderdojo-demo.example"
            guardian_password = generate_password()
            guardian = User(
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
                    account = User(
                        username=child_username,
                        first_name=child_first_name,
                        account_type=User.NINJA,
                    )
                    account.set_password(child_password)
                    account.save()
                    child_logins_created += 1
                    child_credential_rows.append((child_username, "", child_password))

                ninja = Ninja.objects.create(
                    name=f"{child_first_name} {last_name}",
                    account=account,
                    home_dojo=rng.choice(dojos) if dojos else None,
                    member_since=today - timedelta(days=rng.randint(30, 5 * 365)),
                )
                Guardianship.objects.create(guardian=guardian, ninja=ninja)
                use_library_image(ninja, "photo", "ninjas", rng.choice(KID_AVATAR_FILES), save=True)
                children_created += 1

        # Backfill: children seeded before Ninja.photo/home_dojo/
        # member_since were set this way (guardians already existing skip
        # the loop above entirely, so this is the only path that reaches them).
        for ninja in Ninja.objects.all():
            dirty_fields = []
            if not ninja.photo:
                use_library_image(ninja, "photo", "ninjas", rng.choice(KID_AVATAR_FILES))
                dirty_fields.append("photo")
            if not ninja.home_dojo_id and dojos:
                ninja.home_dojo = rng.choice(dojos)
                dirty_fields.append("home_dojo")
            if not ninja.date_of_birth:
                # Per-ninja RNG, so adding this didn't shift the shared stream.
                ninja_rng = random.Random(f"ninja-dob-{ninja.id}")
                ninja.date_of_birth = today - timedelta(days=ninja_rng.randint(7 * 365 + 2, 17 * 365))
                dirty_fields.append("date_of_birth")
            if not ninja.member_since:
                ninja.member_since = today - timedelta(days=rng.randint(30, 5 * 365))
                dirty_fields.append("member_since")
            if dirty_fields:
                ninja.save(update_fields=dirty_fields)

        # A couple of ninjas with their own login help out at their home
        # dojo: youth mentors, promoted by that dojo's champion.
        promoted = 0
        for ninja in Ninja.objects.exclude(account=None).exclude(home_dojo=None).order_by("id")[:3]:
            champion = ninja.home_dojo.champion_membership
            if champion is None or DojoMembership.objects.filter(dojo=ninja.home_dojo, user=ninja.account).exists():
                continue
            DojoMembership.objects.create(
                dojo=ninja.home_dojo, user=ninja.account, role=DojoMembership.YOUTH_MENTOR,
                status=DojoMembership.ACTIVE, promoted_by=champion, requested_by=champion.user,
                joined_at=timezone.now(),
            )
            promoted += 1

        if guardian_credential_rows:
            write_credentials("guardian", guardian_credential_rows)
        if child_credential_rows:
            write_credentials("child_account", child_credential_rows)

        self.stdout.write(self.style.SUCCESS(
            f"Done. guardians={guardians_created} children={children_created} "
            f"child_logins={child_logins_created}. Credentials for newly seeded accounts "
            f"written to {CREDENTIALS_FILE}"
        ))
