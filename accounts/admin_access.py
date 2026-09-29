"""Time-boxed access to the Django admin (DATA_MODEL.md §23).

An organisation role opens the organisation dashboard (/manage/) all the
time, but the Django admin only for `ADMIN_ACCESS_HOURS` at a time, after
asking for it with a reason (`request_access`). The ask and its end are
`AdminAccessGrant` rows, recorded in the audit log; the other organisation
admins get a notification. `User.is_staff` follows the grants
(`sync_staff`): on while one is open, off otherwise, except for superusers,
whose access is a technical intervention on the server and never
time-boxed. The admin site also checks for an open grant on every request
(`may_use_admin`), so access stops at the minute even when
`close_expired` (a beat job) runs late.

Views only call these functions; `AdminAccessError` carries a user-facing
message.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .models import AdminAccessGrant, OrganisationRole, User

ADMIN_ACCESS_HOURS = 12
BELGIAN_TIME = ZoneInfo("Europe/Brussels")


class AdminAccessError(Exception):
    """A user-facing reason access can't be given or ended."""


def open_grant(user):
    """The account's open grant, or None."""
    if not user.is_authenticated:
        return None
    return AdminAccessGrant.objects.open().filter(account=user).first()


def may_ask(user):
    """Holds an organisation role, so may ask for the Django admin."""
    return user.is_authenticated and user.account_type == User.ADULT and user.organisation_roles.exists()


def may_use_admin(user):
    """What the admin site asks on top of Django's own check: a superuser,
    or an open grant."""
    return user.is_superuser or open_grant(user) is not None


def sync_staff(user):
    """`is_staff` on exactly while the account may use the Django admin."""
    needs_staff = user.is_superuser or AdminAccessGrant.objects.open().filter(account=user).exists()
    if user.is_staff != needs_staff:
        user.is_staff = needs_staff
        user.save(update_fields=["is_staff"])


def until_label(grant):
    """The end time as people read it (Belgian time)."""
    return timezone.localtime(grant.expires_at, BELGIAN_TIME).strftime("%H:%M")


@transaction.atomic
def request_access(user, reason):
    reason = (reason or "").strip()
    if not may_ask(user):
        raise AdminAccessError(_("Only an account with an organisation role can ask for the Django admin."))
    if not reason:
        raise AdminAccessError(_("Say why you need the Django admin."))
    if open_grant(user) is not None:
        raise AdminAccessError(_("You already have access to the Django admin."))
    now = timezone.now()
    grant = AdminAccessGrant.objects.create(
        account=user, reason=reason, started_at=now, expires_at=now + timedelta(hours=ADMIN_ACCESS_HOURS)
    )
    sync_staff(user)
    transaction.on_commit(lambda: _notify_admins(grant))
    return grant


def _notify_admins(grant):
    """Every other organisation admin gets a dashboard notification."""
    from notifications.services import notify

    admins = User.objects.filter(
        organisation_roles__role=OrganisationRole.ADMIN, is_active=True, account_type=User.ADULT
    ).exclude(pk=grant.account_id)
    url = reverse("manage_people")
    for admin in admins.distinct():
        notify(
            admin,
            gettext_lazy("%(name)s opened access to the Django admin until %(until)s: %(reason)s"),
            url=url,
            params={"name": grant.account.team_name, "until": until_label(grant), "reason": grant.reason},
            organisation=True,
        )


def end(grant, by=None, end_reason=AdminAccessGrant.ENDED):
    """Ends an open grant now (the holder, `by` someone else, or the job)."""
    if not grant.is_open and end_reason != AdminAccessGrant.EXPIRED:
        raise AdminAccessError(_("This access has already ended."))
    grant.ended_at = min(timezone.now(), grant.expires_at)
    grant.ended_by = by
    grant.end_reason = end_reason
    grant.save(update_fields=["ended_at", "ended_by", "end_reason"])
    sync_staff(grant.account)
    return grant


def end_for(user, by=None, end_reason=AdminAccessGrant.ENDED):
    """Ends the account's open grant, if any."""
    grant = open_grant(user)
    if grant is not None:
        end(grant, by=by, end_reason=end_reason)
    return grant


def close_expired():
    """Closes every grant whose time is up (through save(), so the audit
    log records it) and takes staff status away; returns how many."""
    now = timezone.now()
    closed = 0
    for grant in AdminAccessGrant.objects.filter(ended_at__isnull=True, expires_at__lte=now):
        end(grant, end_reason=AdminAccessGrant.EXPIRED)
        closed += 1
    # Staff status left on without an open grant (e.g. set by hand).
    for user in User.objects.filter(is_staff=True, is_superuser=False):
        sync_staff(user)
    return closed
