"""A child's own login, managed by their guardian (DATA_MODEL.md §17).

A guardian gives a ninja a login (a User of type ninja, `Ninja.account`)
with the child's own email address; the child gets a mail with a link to
choose their password. The guardian can remove it again: the account is
deleted, unless it was ever on a dojo's team (a youth mentor), because
`Event.team` points at its memberships. Such an account is disabled
(`is_active=False`) and its memberships end (dormant); giving the child a
login again switches that same account back on, with a fresh password.

The guardian keeps editing the child's details either way; the login only
lets the child see their own page and sign themselves up for sessions.
Views only call these functions; `ChildAccountError` carries a message for
the guardian.
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.text import slugify
from django.utils.translation import gettext as _

from .models import User
from .provisioning import unique_username

DELETED = "deleted"
DISABLED = "disabled"


class ChildAccountError(Exception):
    """A user-facing reason the change can't be made."""


def has_active_login(ninja):
    return ninja.account is not None and ninja.account.is_active


def _clean_email(email, account=None):
    email = (email or "").strip()
    if not email:
        raise ChildAccountError(_("Your child's own email address is needed for a login."))
    try:
        validate_email(email)
    except ValidationError:
        raise ChildAccountError(_("Enter a valid email address.")) from None
    taken = User.objects.filter(email__iexact=email)
    if account is not None:
        taken = taken.exclude(pk=account.pk)
    if taken.exists():
        raise ChildAccountError(_("An account already exists with this email."))
    return email


def set_password_url(account):
    """A link to choose a password: Django's password-reset confirm page.
    It stops working once the password is set (the token covers it)."""
    path = reverse(
        "password_reset_confirm",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(account.pk)),
            "token": default_token_generator.make_token(account),
        },
    )
    return settings.SITE_URL + path


def send_login_mail(guardian, account):
    """The child's first mail: a link to choose a password, or, for a login
    on a login link, the first login link (DATA_MODEL.md §24)."""
    from mailing.categories import MailCategory
    from mailing.services import send_or_log

    from .login_links import FIRST_LINK_VALID_DAYS, login_url

    context = {
        "guardian_name": guardian.get_full_name() or guardian.get_username(),
        "username": account.get_username(),
        "uses_link": account.uses_login_link,
        "valid_days": FIRST_LINK_VALID_DAYS,
    }
    if account.uses_login_link:
        context["login_url"] = login_url(account, first=True)
    else:
        context["set_password_url"] = set_password_url(account)
    return send_or_log(account, MailCategory.SERVICE, "ninja_account_created", context)


def waiting_for_first_login(account):
    """Whether the child hasn't used its first mail yet: no password chosen,
    or, on a login link, never logged in. The card then offers to send it
    again."""
    if account.uses_login_link:
        return account.last_login is None
    return not account.has_usable_password()


@transaction.atomic
def give_login(guardian, ninja, email, login_method=User.LOGIN_PASSWORD):
    """Create the child's login, or switch a disabled one back on, and mail
    the child a link to choose a password, or its first login link
    (`login_method`, the guardian's choice, DATA_MODEL.md §24)."""
    account = ninja.account
    if account is not None and account.is_active:
        raise ChildAccountError(_("%(name)s already has a login.") % {"name": ninja.name})
    email = _clean_email(email, account)
    if account is None:
        account = User(
            username=unique_username(slugify(ninja.name) or "ninja"),
            account_type=User.NINJA,
            first_name=ninja.name,
            last_name=ninja.family_name,
            preferred_language=guardian.preferred_language,
        )
    account.is_active = True
    account.email = email
    account.login_method = User.LOGIN_LINK if login_method == User.LOGIN_LINK else User.LOGIN_PASSWORD
    # No password until the child chooses one; a re-enabled login never
    # gets its old password back.
    account.set_unusable_password()
    account.save()
    if ninja.account_id != account.pk:
        ninja.account = account
        ninja.save(update_fields=["account"])
    send_login_mail(guardian, account)
    return account


def resend_login_mail(guardian, ninja):
    """Mail the set-password link, or the first login link, again (a new
    one; the old one keeps working until it's used)."""
    if not has_active_login(ninja):
        raise ChildAccountError(_("%(name)s doesn't have a login.") % {"name": ninja.name})
    return send_login_mail(guardian, ninja.account)


def _active_account(ninja):
    if not has_active_login(ninja):
        raise ChildAccountError(_("%(name)s doesn't have a login.") % {"name": ninja.name})
    return ninja.account


def turn_off_two_step(guardian, ninja):
    """The guardian turns off the child's two-step login (a lost phone):
    what the organisation does for an adult (DATA_MODEL.md §24)."""
    from . import two_step

    account = _active_account(ninja)
    if not two_step.is_on(account):
        raise ChildAccountError(_("%(name)s doesn't use two-step login.") % {"name": ninja.name})
    two_step.turn_off(account, by_guardian=guardian)


def switch_to_password(guardian, ninja):
    """The guardian switches the child's login from a login link back to a
    password: none until the child chooses one, from the set-password mail."""
    from .login_links import LoginLinkError, reset_to_password

    account = _active_account(ninja)
    try:
        account = reset_to_password(account, by_guardian=guardian)
    except LoginLinkError as error:
        raise ChildAccountError(error.message) from None
    send_login_mail(guardian, account)
    return account


def change_email(guardian, ninja, new_email):
    """The guardian changes the address of the child's login, confirmed
    from the new address (accounts.email_change, DATA_MODEL.md §24)."""
    from .email_change import GUARDIAN, EmailChangeError, request_change

    account = _active_account(ninja)
    try:
        request_change(account, new_email, started_by=guardian, started_as=GUARDIAN)
    except EmailChangeError as error:
        raise ChildAccountError(error.message) from None


@transaction.atomic
def remove_login(ninja):
    """Delete the child's login, or disable it if it was ever on a dojo's
    team. Returns DELETED or DISABLED. The ninja itself (registrations,
    belts, badges) is never touched."""
    from dojos.models import DojoMembership
    from dojos.team import leave

    account = ninja.account
    if account is None or not account.is_active:
        raise ChildAccountError(_("%(name)s doesn't have a login.") % {"name": ninja.name})
    memberships = list(account.dojo_memberships.all())
    if not memberships:
        account.delete()
        ninja.account = None
        return DELETED
    for membership in memberships:
        if membership.status != DojoMembership.DORMANT:
            leave(membership)
    account.is_active = False
    account.set_unusable_password()
    account.save(update_fields=["is_active", "password"])
    return DISABLED
