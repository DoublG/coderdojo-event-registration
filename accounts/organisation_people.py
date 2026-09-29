"""Who holds which organisation role, managed on the organisation dashboard's
People pages (DATA_MODEL.md §23). The roles themselves stay fixed in code
(accounts.organisation); this grants and revokes them, with these rules:

- nobody changes their own roles;
- there is always at least one account with the `admin` role;
- only active adult accounts, never a ninja's login or a service account;
- superusers are never made or unmade here (that's done on the server).

Every change goes through `OrganisationRole.save()`/`delete()`, so the
signals keep the groups in step (and end open Django admin access with the
last role) and the audit log records it; the person gets a mail. Views only
call these functions; `OrganisationPeopleError` carries a user-facing
message.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import admin_access, sign_in
from .models import AdminAccessGrant, OrganisationRole, User

# The roles in the order the pages show them, with what each opens.
ROLES = [
    (
        OrganisationRole.ADMIN,
        gettext_lazy("Admin"),
        gettext_lazy(
            "The organisation dashboard: campaigns, journeys, segments, mail templates, promotions, sponsors, "
            "awards, privacy, sign-in security and these People pages."
        ),
    ),
    (
        OrganisationRole.REVIEWER,
        gettext_lazy("Background-check reviewer"),
        gettext_lazy(
            "Background checks and applications. Reads criminal-record extracts: only give it to the people "
            "who need it."
        ),
    ),
    (
        OrganisationRole.BOARD,
        gettext_lazy("Board"),
        gettext_lazy("Read-only oversight, in the Django admin."),
    ),
]
ROLE_LABELS = {role: label for role, label, _description in ROLES}


class OrganisationPeopleError(Exception):
    """A user-facing reason the change can't be made."""


def holders():
    """Every account holding an organisation role, with its roles."""
    return (
        User.objects.filter(organisation_roles__isnull=False)
        .distinct()
        .prefetch_related("organisation_roles")
        .order_by("last_name", "first_name", "username")
    )


def superusers():
    return User.objects.filter(is_superuser=True, is_active=True).order_by("username")


def roles_of(account):
    return set(account.organisation_roles.values_list("role", flat=True))


def needs_sign_in_setup(account):
    """The sign-in policy asks this account for two-step login (or a passkey)
    and it hasn't set that up yet."""
    enforced, _upcoming = sign_in.requirements_for(account)
    return sign_in.status(account, True, enforced) == sign_in.NEEDS_SETUP


def _check_account(account, by):
    if account.pk == by.pk:
        raise OrganisationPeopleError(_("You can't change your own roles: ask another organisation admin."))
    if account.account_type != User.ADULT or not account.is_active:
        raise OrganisationPeopleError(_("Only an active adult account can have an organisation role."))


@transaction.atomic
def set_roles(account, roles, by):
    """Give `account` exactly `roles`; returns (added, removed)."""
    roles = set(roles)
    unknown = roles - {role for role, _label, _description in ROLES}
    if unknown:
        raise OrganisationPeopleError(_("Unknown role."))
    _check_account(account, by)
    current = roles_of(account)
    added, removed = roles - current, current - roles
    if OrganisationRole.ADMIN in removed and not (
        OrganisationRole.objects.filter(role=OrganisationRole.ADMIN, account__is_active=True)
        .exclude(account=account)
        .exists()
    ):
        raise OrganisationPeopleError(_("The organisation needs at least one admin: make someone else admin first."))
    for role in sorted(added):
        OrganisationRole.objects.create(account=account, role=role)
    for row in account.organisation_roles.filter(role__in=removed):
        row.delete()
    if added or removed:
        transaction.on_commit(lambda: _mail(account, by))
    return added, removed


def _mail(account, by):
    from django.conf import settings

    from mailing.categories import MailCategory
    from mailing.services import send_or_log

    roles = [role for role, _label, _description in ROLES if role in roles_of(account)]
    send_or_log(
        account,
        MailCategory.SERVICE,
        "organisation_role_changed",
        {
            "roles": roles,
            "changed_by": by.team_name,
            "manage_url": settings.SITE_URL + reverse("manage_home"),
            "contact_url": settings.SITE_URL + reverse("contact"),
        },
    )


def end_access(grant, by):
    """An admin ends someone's open Django admin access."""
    if not grant.is_open:
        raise OrganisationPeopleError(_("This access has already ended."))
    end_reason = AdminAccessGrant.ENDED if grant.account_id == by.pk else AdminAccessGrant.REVOKED
    return admin_access.end(grant, by=by, end_reason=end_reason)


def role_history(account):
    """The audit log's entries for this account's organisation roles, newest
    first: (entry, role, granted) tuples."""
    from auditlog.models import LogEntry

    content_type = ContentType.objects.get_for_model(OrganisationRole)
    pk = str(account.pk)
    history = []
    for entry in LogEntry.objects.filter(content_type=content_type).select_related("actor").order_by("-timestamp"):
        changes = entry.changes if isinstance(entry.changes, dict) else {}
        account_change = changes.get("account") or []
        if pk not in account_change:
            continue
        role = next((value for value in changes.get("role", []) if value and value != "None"), "")
        history.append((entry, ROLE_LABELS.get(role, role), entry.action == LogEntry.Action.CREATE))
    return history
