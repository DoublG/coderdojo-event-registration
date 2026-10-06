"""The one way to send mail: send() renders the template and queues an
EmailMessage row; the Celery dispatcher (mailing.tasks) does the actual
sending. Nothing uses Django's send_mail or a task's .delay to send a mail
(DATA_MODEL.md §11, "Sending pipeline")."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.urls import reverse

from .categories import CAN_OPT_OUT, PRIORITY, MailCategory, categories_for
from .models import EmailMessage, EmailSuppression
from .preferences import is_dojo_muted, is_subscribed
from .rendering import FALLBACK_LANGUAGE, TemplateMissing, render

if TYPE_CHECKING:  # types only
    from accounts.models import User
    from dojos.models import Dojo

logger = logging.getLogger(__name__)

UNSUBSCRIBE_SALT = "mailing.unsubscribe"


def unsubscribe_token(user: "User", category: str, dojo: "Dojo | int | None" = None) -> str:
    """`dojo` (a Dojo or its id) for a dojo's news: the page then also offers
    to mute only that dojo."""
    data: dict[str, object] = {"u": user.pk, "c": category}
    if dojo is not None:
        data["d"] = getattr(dojo, "pk", dojo)
    return signing.dumps(data, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token: str) -> tuple[int, str, int | None]:
    """(user_id, category, dojo_id or None), or raises signing.BadSignature.
    No expiry: an unsubscribe link in an old mail must keep working."""
    data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    return data["u"], data["c"], data.get("d")


def unsubscribe_url(user: "User", category: str, dojo: "Dojo | int | None" = None) -> str:
    token = unsubscribe_token(user, category, dojo if category == MailCategory.DOJO_NEWS else None)
    return settings.SITE_URL + reverse("mail_unsubscribe", kwargs={"token": token})


def is_suppressed_address(email: str) -> bool:
    return EmailSuppression.objects.filter(email=email.strip().lower()).exists()


# Why a mail wasn't sent (EmailMessage.status_reason); a dojo's mail queue
# shows them in words (campaigns.dojo_views).
INACTIVE = "The account is inactive."
WRONG_ACCOUNT_TYPE = "This kind of mail isn't sent to this kind of account."
NOT_SUBSCRIBED = "The recipient hasn't subscribed to this kind of mail."
MUTED_DOJO = "The recipient muted this dojo's news."
NO_ADDRESS = "The account has no email address."
BLOCKED = "The address is blocked (bounce, complaint or by hand)."


def suppressed_reason(
    user: "User", category: str, address: str | None, test: bool = False, dojo: "Dojo | int | None" = None
) -> str:
    """Why `user` mustn't get mail in `category` at `address` right now, or
    "". Checked when a mail is queued and again right before it's sent (a
    campaign can take a while to go out, and people unsubscribe meanwhile).
    A test mail skips the preference checks, never the blocks. `dojo` (a
    Dojo or its id) is the dojo a `dojo_news` mail is from, which the
    account may have muted."""
    if not user.is_active:
        return INACTIVE
    if category not in categories_for(user):
        return WRONG_ACCOUNT_TYPE
    if not test and not is_subscribed(user, category):
        return NOT_SUBSCRIBED
    if not test and dojo is not None and category == MailCategory.DOJO_NEWS and is_dojo_muted(user, dojo):
        return MUTED_DOJO
    if not address:
        return NO_ADDRESS
    if is_suppressed_address(address):
        return BLOCKED
    return ""


def send(
    user: "User",
    category: str,
    template_key: str,
    context: dict[str, Any] | None = None,
    *,
    idempotency_key: str | None = None,
    # A campaigns.Campaign: mailing never imports campaigns (a higher layer), not even for a type.
    campaign: Any = None,
    send_after: datetime | None = None,
    test: bool = False,
    address: str | None = None,
    dojo: "Dojo | None" = None,
    reply_to: str = "",
) -> EmailMessage:
    """Queue one mail to `user`. Renders `template_key` in the account's
    language now (so the row records exactly what was sent) and returns
    the EmailMessage: `pending`, or `suppressed` with the reason when the
    account can't or doesn't want to get it. With `idempotency_key`, a
    second call with the same key returns the first row and queues nothing.
    `test` is for a campaign's test mail to its own author: marked
    "[Test]", and the author's preferences don't apply (blocks still do).
    `address` sends account (`service`) mail somewhere other than
    `user.email`: the confirmation of a new address before it's the
    account's (accounts.email_change). Blocks apply to it as to any other.
    `dojo` is the dojo a `dojo_news` mail is from: not sent to an account
    that muted it, and its unsubscribe link can mute just that dojo.
    `reply_to` is where replies go (a dojo mailing's dojo address)."""
    if idempotency_key and (existing := EmailMessage.objects.filter(idempotency_key=idempotency_key).first()):
        return existing

    if address is not None and category != MailCategory.SERVICE:
        raise ValueError("Only service mail can go to an address other than the account's.")
    language = user.preferred_language or FALLBACK_LANGUAGE
    address = (user.email if address is None else address).strip()
    context = {
        "recipient_name": user.first_name or user.get_username(),
        "site_url": settings.SITE_URL,
        **({"unsubscribe_url": unsubscribe_url(user, category, dojo)} if CAN_OPT_OUT[MailCategory(category)] else {}),
        **(context or {}),
    }
    subject, body = render(template_key, language, context)
    if test:
        subject = f"[Test] {subject}"
    reason = suppressed_reason(user, category, address, test=test, dojo=dojo)

    try:
        with transaction.atomic():
            return EmailMessage.objects.create(
                user=user,
                recipient=address,
                category=category,
                template_key=template_key,
                language=language,
                subject=subject,
                body=body,
                campaign=campaign,
                dojo=dojo,
                reply_to=reply_to,
                status=EmailMessage.Status.SUPPRESSED if reason else EmailMessage.Status.PENDING,
                status_reason=reason,
                priority=PRIORITY[MailCategory(category)],
                send_after=send_after,
                idempotency_key=idempotency_key,
                is_test=test,
            )
    except IntegrityError:
        # The same idempotency key queued concurrently: that row wins.
        if idempotency_key:
            return EmailMessage.objects.get(idempotency_key=idempotency_key)
        raise


def send_to_address(
    address: str, template_key: str, context: dict[str, Any] | None = None, *, language: str, name: str = ""
) -> EmailMessage:
    """Queue one service mail to someone without an account yet: an
    invitation to the organisation (accounts.invitations, DATA_MODEL.md
    §23). Like send(), rendered now in `language` and blocked for a
    suppressed address, but with no account: no preferences to check, and
    the row's `user` stays empty."""
    address = (address or "").strip()
    language = language or FALLBACK_LANGUAGE
    context = {"recipient_name": name, "site_url": settings.SITE_URL, **(context or {})}
    subject, body = render(template_key, language, context)
    if not address:
        reason = "No address."
    elif is_suppressed_address(address):
        reason = "The address is blocked (bounce, complaint or by hand)."
    else:
        reason = ""
    return EmailMessage.objects.create(
        user=None,
        recipient=address,
        category=MailCategory.SERVICE,
        template_key=template_key,
        language=language,
        subject=subject,
        body=body,
        status=EmailMessage.Status.SUPPRESSED if reason else EmailMessage.Status.PENDING,
        status_reason=reason,
        priority=PRIORITY[MailCategory.SERVICE],
    )


def send_or_log(
    user: "User", category: str, template_key: str, context: dict[str, Any] | None = None, **kwargs: Any
) -> EmailMessage | None:
    """send(), but a missing template is logged instead of raised: for mail
    sent as a side effect of something else (a reviewer's decision, a
    password reset), which must never fail because of the mail."""
    try:
        return send(user, category, template_key, context, **kwargs)
    except TemplateMissing:
        logger.exception("mail template %s is missing: nothing sent to %s", template_key, user)
        return None
