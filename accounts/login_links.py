"""Logging in with an emailed link (DATA_MODEL.md §24).

An account logs in with a password or with a login link, its holder's own
choice (`User.login_method`). An account on a link has no usable password;
each login it asks for a link at /login/link/ and opens it
(accounts.views.LoginLinkView, the same login steps as /login/, so two-step
login still follows).

Nothing is stored: a link is a token in the style of Django's password
reset, over the account's password hash, last login, email address and
login method. So it works once (logging in changes `last_login`), stops
working when the address or the method changes, and expires after
VALID_MINUTES. The first link after sign-up or after a guardian gave a child
a login lasts longer (FIRST_LINK_VALID_DAYS) and only until that first
login.

Switching to a link is confirmed from the mailbox (`request_switch_to_link`,
then `switch_to_link` from the mailed page), so a mailbox that never gets
our mail can't lock anyone out. Switching back is setting a password
(`switch_to_password`). Views only call these functions; `LoginLinkError`
carries a message for the person.
"""

import hashlib
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import base36_to_int, urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext as _

from mailing.categories import MailCategory
from mailing.services import send_or_log

from .models import User
from .security_mail import LOGIN_METHOD_CHANGED, send_security_mail

if TYPE_CHECKING:
    from mailing.models import EmailMessage

logger = logging.getLogger(__name__)

VALID_MINUTES = 15
FIRST_LINK_VALID_DAYS = 3
SWITCH_VALID_HOURS = 24
# One mail a minute per address: asking for a link mails the account.
REQUEST_INTERVAL_SECONDS = 60
# Who can log in at all: people, never the API's technical accounts.
PEOPLE = (User.ADULT, User.NINJA)


class LoginLinkError(Exception):
    """Something that can't be done, with a message for the person."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _TimedTokens(PasswordResetTokenGenerator):
    """A PasswordResetTokenGenerator with its own validity (Django's uses
    PASSWORD_RESET_TIMEOUT for every token)."""

    valid_seconds = 0

    def check_token(self, user: User | None, token: str | None) -> bool:
        if not super().check_token(user, token):
            return False
        try:
            timestamp = base36_to_int((token or "").split("-")[0])
        except ValueError:
            return False
        return self._num_seconds(self._now()) - timestamp <= self.valid_seconds


class LoginLinkTokens(_TimedTokens):
    key_salt = "accounts.login_links.LoginLinkTokens"
    valid_seconds = VALID_MINUTES * 60

    def _make_hash_value(self, user: User, timestamp: int) -> str:
        last_login = "" if user.last_login is None else user.last_login.replace(microsecond=0, tzinfo=None)
        email = (user.email or "").strip().lower()
        return f"{user.pk}{user.password}{last_login}{timestamp}{email}{user.login_method}{user.is_active}"


class FirstLoginLinkTokens(LoginLinkTokens):
    """The first link, after sign-up or a login a guardian gave: longer, and
    over the empty last login, so it ends with that first login."""

    key_salt = "accounts.login_links.FirstLoginLinkTokens"
    valid_seconds = FIRST_LINK_VALID_DAYS * 24 * 3600


class SwitchTokens(_TimedTokens):
    """The confirmation of a switch to a login link: over the password and
    the method, so it's gone once the switch is made or the password changes."""

    key_salt = "accounts.login_links.SwitchTokens"
    valid_seconds = SWITCH_VALID_HOURS * 3600

    def _make_hash_value(self, user: User, timestamp: int) -> str:
        email = (user.email or "").strip().lower()
        return f"{user.pk}{user.password}{timestamp}{email}{user.login_method}{user.is_active}"


login_tokens = LoginLinkTokens()
first_login_tokens = FirstLoginLinkTokens()
switch_tokens = SwitchTokens()


def _uid(user: User) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def _user_from_uid(uidb64: str) -> User | None:
    try:
        pk = int(force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError):
        return None
    return User.objects.filter(pk=pk, is_active=True, account_type__in=PEOPLE).first()


def _with_next(url: str, next_url: str | None) -> str:
    return f"{url}?{urlencode({'next': next_url})}" if next_url else url


def login_url(user: User, next_url: str | None = None, first: bool = False) -> str:
    tokens = first_login_tokens if first else login_tokens
    path = reverse("login_link", kwargs={"uidb64": _uid(user), "token": tokens.make_token(user)})
    return _with_next(settings.SITE_URL + path, next_url)


def user_from_link(uidb64: str, token: str) -> User | None:
    """The account a login link is for, or None when it's broken, expired,
    already used, or the account doesn't log in with a link (any more)."""
    user = _user_from_uid(uidb64)
    if user is None or not user.uses_login_link:
        return None
    if login_tokens.check_token(user, token) or first_login_tokens.check_token(user, token):
        return user
    return None


def _throttle(key: str) -> None:
    # cache.add is False when the key exists; None when the cache is down
    # (IGNORE_EXCEPTIONS), and then the request goes ahead.
    if cache.add(key, 1, REQUEST_INTERVAL_SECONDS) is False:
        raise LoginLinkError(_("We just sent a mail. Please wait a minute before asking again."))


def send_login_link(user: User, next_url: str | None = None, first: bool = False) -> "EmailMessage | None":
    """Mail `user` a login link (the `login_link` template)."""
    return send_or_log(
        user,
        MailCategory.SERVICE,
        "login_link",
        {
            "login_url": login_url(user, next_url, first=first),
            "first": first,
            "valid_minutes": VALID_MINUTES,
            "valid_days": FIRST_LINK_VALID_DAYS,
        },
    )


def _password_reset_url(user: User) -> str:
    path = reverse(
        "password_reset_confirm",
        kwargs={"uidb64": _uid(user), "token": default_token_generator.make_token(user)},
    )
    return settings.SITE_URL + path


def request_link(email: str | None, next_url: str | None = None) -> None:
    """Someone asks for a login link for `email`. Whatever the answer, the
    page says the same, so it never tells whether an account exists: an
    account on a link gets one, an account on a password gets a mail saying
    so (with a password-reset link), an unknown address gets nothing. One
    request a minute per address, known or not."""
    address = (email or "").strip()
    digest = hashlib.sha256(address.lower().encode()).hexdigest()
    _throttle(f"accounts:login-link:{digest}")
    matches = list(User.objects.filter(email__iexact=address, is_active=True, account_type__in=PEOPLE)[:2])
    if len(matches) != 1:  # none, or an address two accounts share (the login refuses those too)
        return
    user = matches[0]
    if user.uses_login_link:
        send_login_link(user, next_url)
    else:
        send_or_log(
            user,
            MailCategory.SERVICE,
            "login_link_not_available",
            {
                "reset_url": _password_reset_url(user),
                "security_url": settings.SITE_URL + reverse("account_security"),
            },
        )


def reauth_link(user: User, next_url: str | None) -> None:
    """A login link for someone who is logged in but has to confirm it's
    them (accounts.reauth): it brings them back to `next_url`."""
    if not user.uses_login_link:
        raise LoginLinkError(_("This account logs in with a password."))
    _throttle(f"accounts:login-link:user:{user.pk}")
    send_login_link(user, next_url)


# --- Switching --------------------------------------------------------------


def switch_url(user: User) -> str:
    path = reverse(
        "account_login_method_confirm", kwargs={"uidb64": _uid(user), "token": switch_tokens.make_token(user)}
    )
    return settings.SITE_URL + path


def request_switch_to_link(user: User) -> None:
    """Mail `user` the confirmation of a switch to a login link. Nothing
    changes until it's opened."""
    if user.uses_login_link:
        raise LoginLinkError(_("You already log in with a link."))
    if not user.email:
        raise LoginLinkError(_("A login link needs an email address on the account."))
    _throttle(f"accounts:login-link:switch:{user.pk}")
    send_or_log(
        user,
        MailCategory.SERVICE,
        "login_method_confirm",
        {"confirm_url": switch_url(user), "valid_hours": SWITCH_VALID_HOURS},
    )


def user_from_switch_link(uidb64: str, token: str) -> User | None:
    user = _user_from_uid(uidb64)
    if user is None or user.uses_login_link or not switch_tokens.check_token(user, token):
        return None
    return user


def _changed(user: User, by_guardian: User | None = None) -> None:
    send_security_mail(
        user,
        "login_method_changed",
        change=LOGIN_METHOD_CHANGED,
        method=user.login_method,
        by_guardian=by_guardian.get_full_name() if by_guardian else "",
        contact_url=settings.SITE_URL + reverse("contact"),
    )


def switch_to_link(user: User) -> User:
    """Log in with a link from now on: the password goes (so the other
    sessions and remembered browsers end). Checked again under a lock, so
    two clicks switch once. The caller keeps its own session with
    update_session_auth_hash."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if user.uses_login_link:
            raise LoginLinkError(_("You already log in with a link."))
        user.login_method = User.LOGIN_LINK
        user.set_unusable_password()
        user.must_change_password = False
        user.save(update_fields=["login_method", "password", "must_change_password"])
    _changed(user)
    return user


def switch_to_password(user: User, raw_password: str) -> User:
    """Log in with this password from now on (from a session that just
    confirmed it's them, accounts.reauth)."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        was_link = user.uses_login_link
        user.login_method = User.LOGIN_PASSWORD
        user.set_password(raw_password)
        user.must_change_password = False
        user.save(update_fields=["login_method", "password", "must_change_password"])
    if was_link:
        _changed(user)
    return user


def reset_to_password(user: User, by_guardian: User) -> User:
    """A guardian switches their child's login back to a password: no
    password until the child chooses one (the set-password mail,
    accounts.child_accounts)."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if not user.uses_login_link:
            raise LoginLinkError(_("This login already uses a password."))
        user.login_method = User.LOGIN_PASSWORD
        user.set_unusable_password()
        user.save(update_fields=["login_method", "password"])
    _changed(user, by_guardian=by_guardian)
    return user
