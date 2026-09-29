"""Changing an account's email address (DATA_MODEL.md §22).

The address is a login name and where every mail goes, so it never changes
straight from a form: request_change() mails a signed link to the new
address, and only confirm_change() (from that link) changes it, telling the
old address. The family asks with its password (accounts.views.change_email);
an organisation admin can start it for a family that lost its old mailbox
(privacy.views.manage_privacy_email), and a guardian for their child's own
login (accounts.child_accounts.change_email, DATA_MODEL.md §24); those links
work without logging in. Nothing is stored until the change is made: the link carries
the account, the new address and a fingerprint of the current one, so it
stops working once the address has changed (single use) or after
VALID_HOURS.
"""

import logging
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext as _

from mailing.categories import MailCategory
from mailing.rendering import TemplateMissing
from mailing.services import is_suppressed_address, send, send_or_log

from .models import User
from .security_mail import EMAIL_CHANGED, tell_guardians

logger = logging.getLogger(__name__)

SALT = "accounts.email_change"
BELGIAN_TIME = ZoneInfo("Europe/Brussels")
VALID_HOURS = 24
# One request per account per minute: the form mails any address it's given.
REQUEST_INTERVAL_SECONDS = 60

# Who started a change, when it wasn't the account holder (`started_as`).
ORGANISATION = "organisation"
GUARDIAN = "guardian"


class EmailChangeError(Exception):
    """A change that can't be made, with a message for the person."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


@dataclass
class ChangeRequest:
    """What a confirmation link asks for."""

    user: User
    new_email: str
    started_by: User | None = None
    started_as: str | None = None  # ORGANISATION, GUARDIAN, or None: the account holder


def _same(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


def check_new_address(user, new_email):
    """Raise EmailChangeError when `user` can't move to `new_email`."""
    if _same(new_email, user.email):
        raise EmailChangeError(_("That's already the account's email address."))
    if User.objects.filter(email__iexact=new_email.strip()).exclude(pk=user.pk).exists():
        raise EmailChangeError(_("An account already exists with this email."))
    if is_suppressed_address(new_email):
        raise EmailChangeError(
            _("We can't send mail to this address: earlier mails to it bounced. Pick another one, or contact us.")
        )


def organisation_blocker(user):
    """Why the organisation can't start a change for `user` from its
    dashboard, or "" when it can. Those accounts are changed in the Django
    admin (as for deleting an account)."""
    if user.is_ninja:
        return _("A child's own login is managed by their parent.")
    if user.is_service:
        return _("This is an API client's technical account.")
    if user.is_superuser:
        return _("This is a technical administrator's account (superuser); change it in the Django admin.")
    if user.organisation_roles.exists():
        return _("This account has an organisation role; change it in the Django admin.")
    if not user.is_active:
        return _("This account is switched off.")
    return ""


def _fingerprint(email):
    """Stands for the current address in a link (which ends up in server
    logs), without showing it."""
    return salted_hmac(SALT, (email or "").strip().lower(), algorithm="sha256").hexdigest()[:16]


def is_guardian_of(guardian, account):
    """Whether `guardian` is a guardian of the child whose own login is `account`."""
    from .models import Guardianship

    return (
        guardian is not None
        and account.is_ninja
        and Guardianship.objects.filter(guardian=guardian, ninja__account=account).exists()
    )


def make_token(user, new_email, started_by=None, started_as=None):
    return signing.dumps(
        {
            "u": user.pk,
            "e": new_email.strip(),
            "o": _fingerprint(user.email),
            "b": started_by.pk if started_by else None,
            "a": (started_as or ORGANISATION) if started_by else None,
        },
        salt=SALT,
    )


def confirm_url(token):
    return settings.SITE_URL + reverse("confirm_email_change", kwargs={"token": token})


def read_token(token):
    """The ChangeRequest behind a link, or EmailChangeError when it's
    broken, expired or already used (the address has changed since)."""
    try:
        data = signing.loads(token, salt=SALT, max_age=VALID_HOURS * 3600)
    except signing.SignatureExpired:
        raise EmailChangeError(_("This link has expired. Ask for the change again.")) from None
    except signing.BadSignature:
        raise EmailChangeError(_("This link isn't valid.")) from None
    user = User.objects.filter(pk=data["u"], is_active=True).first()
    if user is None:
        raise EmailChangeError(_("This link isn't valid."))
    if _fingerprint(user.email) != data["o"]:
        raise EmailChangeError(_("This link has already been used, or the address changed since."))
    started_by = User.objects.filter(pk=data["b"]).first() if data["b"] else None
    # A link from before `started_as` existed: only the organisation started those.
    started_as = (data.get("a") or ORGANISATION) if started_by else None
    return ChangeRequest(user=user, new_email=data["e"], started_by=started_by, started_as=started_as)


def request_change(user, new_email, started_by=None, started_as=None):
    """Mail a confirmation link for `user`'s new address to that address.
    `started_by` is who started it, if it wasn't the account holder: an
    organisation admin (`started_as` ORGANISATION, the default), or a
    guardian of the child whose login it is (GUARDIAN)."""
    new_email = new_email.strip()
    check_new_address(user, new_email)
    if started_by is not None:
        started_as = started_as or ORGANISATION
        if started_as == GUARDIAN:
            if not is_guardian_of(started_by, user) or not user.is_active:
                raise EmailChangeError(_("Only a child's guardian can change the address of their login."))
        elif blocker := organisation_blocker(user):
            raise EmailChangeError(blocker)
    # cache.add is False when the key exists; None when the cache is down
    # (IGNORE_EXCEPTIONS), and then the request goes ahead.
    if cache.add(f"accounts:email-change:{user.pk}", 1, REQUEST_INTERVAL_SECONDS) is False:
        raise EmailChangeError(_("A confirmation link was just sent. Please wait a minute before asking again."))
    context = {
        "new_email": new_email,
        "old_email": user.email,
        "confirm_url": confirm_url(make_token(user, new_email, started_by, started_as)),
        "valid_hours": VALID_HOURS,
        "by_organisation": started_by is not None and started_as == ORGANISATION,
        "by_guardian": (started_by.get_full_name() or started_by.get_username()) if started_as == GUARDIAN else "",
    }
    try:
        send(user, MailCategory.SERVICE, "email_change_confirm", context, address=new_email)
    except TemplateMissing:
        logger.exception("mail template email_change_confirm is missing: no email change for %s", user)
        raise EmailChangeError(_("We can't send the confirmation mail right now. Please try again later.")) from None


def confirm_change(change):
    """Make the change a link asked for: tell the old address, then save
    the new one (through save(), so the audit log has it). Checked again
    under a lock, so two clicks on the link change it once."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=change.user.pk)
        if not _same(user.email, change.user.email):
            raise EmailChangeError(_("This link has already been used, or the address changed since."))
        if change.started_as == GUARDIAN and not is_guardian_of(change.started_by, user):
            raise EmailChangeError(
                _("This link isn't valid any more: whoever asked for it is no longer the guardian.")
            )
        check_new_address(user, change.new_email)
        # Queued before the save, so it keeps the old address as its recipient.
        send_or_log(
            user,
            MailCategory.SERVICE,
            "email_changed",
            {
                "new_email": change.new_email,
                # Belgian wall-clock time; naive, or |date would turn it back into UTC.
                "changed_at": timezone.localtime(timezone.now(), BELGIAN_TIME).replace(tzinfo=None),
                "contact_url": settings.SITE_URL + reverse("contact"),
            },
        )
        user.email = change.new_email
        user.save(update_fields=["email"])
    # A child's own login: its guardians hear about it too.
    tell_guardians(user, EMAIL_CHANGED, new_email=user.email)
    return user
