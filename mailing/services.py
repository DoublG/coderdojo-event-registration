"""The one way to send mail: send() renders the template and queues an
EmailMessage row; the Celery dispatcher (mailing.tasks) does the actual
sending. Nothing calls send_mail() or a task's .delay() to send a mail
(DATA_MODEL.md §11, "Sending pipeline")."""

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.urls import reverse

from .categories import CAN_OPT_OUT, PRIORITY, categories_for
from .models import EmailMessage, EmailSuppression
from .preferences import is_subscribed
from .rendering import FALLBACK_LANGUAGE, render

UNSUBSCRIBE_SALT = "mailing.unsubscribe"


def unsubscribe_token(user, category):
    return signing.dumps({"u": user.pk, "c": category}, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token):
    """(user_id, category), or raises signing.BadSignature. No expiry: an
    unsubscribe link in an old mail must keep working."""
    data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    return data["u"], data["c"]


def unsubscribe_url(user, category):
    return settings.SITE_URL + reverse("mail_unsubscribe", kwargs={"token": unsubscribe_token(user, category)})


def is_suppressed_address(email):
    return EmailSuppression.objects.filter(email=email.strip().lower()).exists()


def _suppressed_reason(user, category, address):
    if not user.is_active:
        return "The account is inactive."
    if category not in categories_for(user):
        return "This kind of mail isn't sent to this kind of account."
    if not is_subscribed(user, category):
        return "The recipient hasn't subscribed to this kind of mail."
    if not address:
        return "The account has no email address."
    if is_suppressed_address(address):
        return "The address is blocked (bounce, complaint or by hand)."
    return ""


def send(user, category, template_key, context=None, *, idempotency_key=None, campaign=None, send_after=None):
    """Queue one mail to `user`. Renders `template_key` in the account's
    language now (so the row records exactly what was sent) and returns
    the EmailMessage: `pending`, or `suppressed` with the reason when the
    account can't or doesn't want to get it. With `idempotency_key`, a
    second call with the same key returns the first row and queues nothing."""
    if idempotency_key and (existing := EmailMessage.objects.filter(idempotency_key=idempotency_key).first()):
        return existing

    language = user.preferred_language or FALLBACK_LANGUAGE
    address = user.email.strip()
    context = {
        "recipient_name": user.first_name or user.get_username(),
        "site_url": settings.SITE_URL,
        **({"unsubscribe_url": unsubscribe_url(user, category)} if CAN_OPT_OUT[category] else {}),
        **(context or {}),
    }
    subject, body = render(template_key, language, context)
    reason = _suppressed_reason(user, category, address)

    try:
        with transaction.atomic():
            return EmailMessage.objects.create(
                user=user, recipient=address, category=category, template_key=template_key,
                language=language, subject=subject, body=body, campaign=campaign,
                status=EmailMessage.Status.SUPPRESSED if reason else EmailMessage.Status.PENDING,
                status_reason=reason, priority=PRIORITY[category], send_after=send_after,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        # The same idempotency key queued concurrently: that row wins.
        if idempotency_key:
            return EmailMessage.objects.get(idempotency_key=idempotency_key)
        raise
