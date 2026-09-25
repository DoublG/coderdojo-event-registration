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
        raise ChildAccountError("Your child's own email address is needed for a login.")
    try:
        validate_email(email)
    except ValidationError:
        raise ChildAccountError("Enter a valid email address.") from None
    taken = User.objects.filter(email__iexact=email)
    if account is not None:
        taken = taken.exclude(pk=account.pk)
    if taken.exists():
        raise ChildAccountError("An account already exists with this email.")
    return email


def set_password_url(account):
    """A link to choose a password: Django's password-reset confirm page.
    It stops working once the password is set (the token covers it)."""
    path = reverse("password_reset_confirm", kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(account.pk)),
        "token": default_token_generator.make_token(account),
    })
    return settings.SITE_URL + path


def send_login_mail(guardian, account):
    from mailing.categories import MailCategory
    from mailing.services import send_or_log

    return send_or_log(account, MailCategory.SERVICE, "ninja_account_created", {
        "guardian_name": guardian.get_full_name() or guardian.get_username(),
        "username": account.get_username(),
        "set_password_url": set_password_url(account),
    })


@transaction.atomic
def give_login(guardian, ninja, email):
    """Create the child's login, or switch a disabled one back on, and mail
    the child a link to choose a password."""
    account = ninja.account
    if account is not None and account.is_active:
        raise ChildAccountError(f"{ninja.name} already has a login.")
    email = _clean_email(email, account)
    if account is None:
        account = User(
            username=unique_username(slugify(ninja.name) or "ninja"),
            account_type=User.NINJA,
            first_name=ninja.name,
            preferred_language=guardian.preferred_language,
        )
    account.is_active = True
    account.email = email
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
    """Mail the set-password link again (a new one, the old one keeps
    working until a password is set)."""
    if not has_active_login(ninja):
        raise ChildAccountError(f"{ninja.name} doesn't have a login.")
    return send_login_mail(guardian, ninja.account)


@transaction.atomic
def remove_login(ninja):
    """Delete the child's login, or disable it if it was ever on a dojo's
    team. Returns DELETED or DISABLED. The ninja itself (registrations,
    belts, badges) is never touched."""
    from dojos.models import DojoMembership
    from dojos.team import leave

    account = ninja.account
    if account is None or not account.is_active:
        raise ChildAccountError(f"{ninja.name} doesn't have a login.")
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
