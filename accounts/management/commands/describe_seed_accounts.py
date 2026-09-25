from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from accounts.models import User
from accounts.seed_credentials import (
    CREDENTIALS_FILE,
    SEED_EMAIL_DOMAINS,
    _write,
    describe_rows,
    generate_password,
    read_credentials,
)


def _role_for(user):
    if user.is_ninja:
        return "child_account"
    if user.organisation_roles.exists():
        return "organisation"
    roles = set(user.dojo_memberships.values_list("role", flat=True))
    if "champion" in roles:
        return "dojo_owner"
    if "mentor" in roles:
        return "mentor"
    if user.guardianships.exists():
        return "guardian"
    return "adult"


class Command(BaseCommand):
    help = (
        "Refresh the description column of seed_credentials.csv (what a tester can do with each login). With "
        "DEBUG on, seeded accounts missing from the file (demo email domains, or a child login without email) "
        "get a new password and a row, so every seeded login can be tested."
    )

    def handle(self, *args, **options):
        rows = read_credentials()
        restored = 0
        if settings.DEBUG:
            seeded = Q(account_type=User.NINJA, email="")
            for domain in SEED_EMAIL_DOMAINS:
                seeded |= Q(email__iendswith=domain)
            missing = User.objects.filter(seeded).exclude(username__in=[row["username"] for row in rows]).order_by("id")
            for user in missing:
                password = generate_password()
                user.set_password(password)
                user.save(update_fields=["password"])
                rows.append({"role": _role_for(user), "username": user.username, "email": user.email, "password": password})
                restored += 1
        _write(describe_rows(rows))
        self.stdout.write(self.style.SUCCESS(
            f"Done. {len(rows)} logins described in {CREDENTIALS_FILE.name}"
            + (f", {restored} missing seeded logins given a new password." if restored else ".")
        ))
