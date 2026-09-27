from django.core.management.base import BaseCommand
from django.db.models import Q
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts import two_step
from accounts.models import OrganisationRole, User
from accounts.seed_credentials import SEED_EMAIL_DOMAINS
from core.audit import without_audit_log
from dojos.models import Dojo, DojoMembership


def _seeded():
    query = Q()
    for domain in SEED_EMAIL_DOMAINS:
        query |= Q(email__iendswith=domain)
    return User.objects.filter(query, account_type=User.ADULT, is_active=True).order_by("username")


def picks():
    """One seeded account per kind, the same ones on every run: an
    organisation admin, a champion of a normal dojo, a mentor (not a
    champion) and a parent with no role."""
    seeded = _seeded()
    active = Q(dojo_memberships__status=DojoMembership.ACTIVE)
    team = Q(dojo_memberships__isnull=False) | Q(organisation_roles__isnull=False)
    return [
        seeded.filter(organisation_roles__role=OrganisationRole.ADMIN).first(),
        seeded.filter(active, dojo_memberships__role=DojoMembership.CHAMPION)
        .exclude(dojo_memberships__dojo__kind=Dojo.ORGANISATION).first(),
        seeded.filter(active, dojo_memberships__role=DojoMembership.MENTOR)
        .exclude(dojo_memberships__role=DojoMembership.CHAMPION).first(),
        seeded.filter(guardianships__isnull=False).exclude(team).first(),
    ]


class Command(BaseCommand):
    help = (
        "Turn on two-step login (an authenticator app, plus backup codes) for a few seeded accounts: an organisation "
        "admin, a champion, a mentor and a parent. Their app key goes in seed_credentials.csv's totp_secret column "
        "(describe_seed_accounts); `manage.py totp_code <username>` prints the current code. Accounts that already "
        "have two-step login are left alone."
    )

    @without_audit_log
    def handle(self, *args, **options):
        created = []
        for user in filter(None, dict.fromkeys(picks())):
            if two_step.is_on(user):
                continue
            TOTPDevice.objects.create(user=user, name=two_step.DEFAULT_NAME)
            two_step.make_backup_codes(user)
            created.append(user.username)
        self.stdout.write(self.style.SUCCESS(
            f"Two-step login turned on for {len(created)} seeded accounts"
            + (f": {', '.join(created)}." if created else " (already on).")
        ))
