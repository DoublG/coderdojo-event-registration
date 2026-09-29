from django.core.management.base import BaseCommand

from accounts.models import User
from core.audit import without_audit_log
from dojos.models import DojoMembership

from .seed_two_step import _seeded, picks


def link_picks():
    """A seeded parent with no role and a mentor (not a champion) that log in
    with an emailed link (DATA_MODEL.md §24): the same ones on every run, and
    never the accounts seed_two_step picked, so both kinds stay testable."""
    taken = [user.pk for user in picks() if user]
    seeded = _seeded().exclude(pk__in=taken)
    active_mentor = seeded.filter(
        dojo_memberships__status=DojoMembership.ACTIVE, dojo_memberships__role=DojoMembership.MENTOR
    ).exclude(dojo_memberships__role=DojoMembership.CHAMPION)
    parent = seeded.filter(guardianships__isnull=False, dojo_memberships__isnull=True, organisation_roles__isnull=True)
    return [parent.first(), active_mentor.first()]


class Command(BaseCommand):
    help = (
        "Switch a seeded parent and a seeded mentor to logging in with an emailed link (no password). "
        "describe_seed_accounts (end of start.sh) notes it in their seed_credentials.csv row; the links arrive in "
        "Mailpit."
    )

    @without_audit_log
    def handle(self, *args, **options):
        switched = []
        for user in filter(None, dict.fromkeys(link_picks())):
            if user.uses_login_link:
                continue
            user.login_method = User.LOGIN_LINK
            user.set_unusable_password()
            user.save(update_fields=["login_method", "password"])
            switched.append(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Login links for {len(switched)} seeded accounts"
                + (f": {', '.join(user.username for user in switched)}." if switched else " (already on).")
            )
        )
