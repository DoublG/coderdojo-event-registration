"""The mail queue's Celery side (DATA_MODEL.md §11, "Sending pipeline").

- send_pending_emails (beat, every 10 s, `periodic` queue) only dispatches:
  it claims pending rows in priority order and hands them out as
  send_email_batch subtasks.
- send_email_batch (default queue, the mailing worker) sends one chunk over
  one SMTP connection. Celery does the rate limiting (`rate_limit`) and
  the retries (`autoretry_for` + backoff).
- requeue_stuck_emails (beat, every 15 min) puts rows whose subtask got
  lost back in the queue, and logs how the queue is doing.
"""

import email.policy
import logging
import smtplib
from datetime import timedelta
from email.utils import make_msgid
from urllib.parse import urlparse

from celery import Task, group, shared_task
from django.conf import settings
from django.core import mail
from django.db import transaction
from django.db.models import Min, Q
from django.utils import timezone

from .categories import CAN_OPT_OUT
from .models import EmailMessage
from .services import unsubscribe_url

logger = logging.getLogger(__name__)

Status = EmailMessage.Status


class TransientSendError(Exception):
    """The SMTP server can't take mail right now (down, timeout, 4xx):
    retry the batch later."""


def _claim_pending():
    """Claim the next pending rows (priority first) and mark them `sending`.
    Never claims more than MAILING_CLAIM_LIMIT rows in flight, so the
    broker holds only a few batches' worth and priority stays in the
    database: a password reset queued behind a big campaign is claimed on
    the next run. skip_locked keeps overlapping runs from claiming the same
    rows. Returns the claimed ids."""
    now = timezone.now()
    with transaction.atomic():
        room = settings.MAILING_CLAIM_LIMIT - EmailMessage.objects.filter(status=Status.SENDING).count()
        if room <= 0:
            return []
        ids = list(
            EmailMessage.objects.select_for_update(skip_locked=True)
            .filter(status=Status.PENDING)
            .filter(Q(send_after__isnull=True) | Q(send_after__lte=now))
            .order_by("priority", "created_at", "id")
            .values_list("id", flat=True)[:room]
        )
        EmailMessage.objects.filter(pk__in=ids).update(status=Status.SENDING, claimed_at=now)
    return ids


def _chunks(ids, size):
    return [ids[i:i + size] for i in range(0, len(ids), size)]


@shared_task
def send_pending_emails():
    ids = _claim_pending()
    if ids:
        group(send_email_batch.s(chunk) for chunk in _chunks(ids, settings.MAILING_BATCH_SIZE)).apply_async()
    return len(ids)


class QueuedEmail(mail.EmailMessage):
    """Header lines up to SMTP's 998-character limit instead of folding at
    78. A long List-Unsubscribe URL has nowhere to fold, and the email
    package would then RFC 2047-encode it (=?utf-8?q?...), which that
    structured header doesn't allow: mail clients wouldn't offer one-click
    unsubscribe. Whatever policy the backend asks for (the SMTP backend
    passes email.policy.SMTP) is kept, only its line length changes."""

    def message(self, *, policy=email.policy.default):
        return super().message(policy=policy.clone(max_line_length=998))


def _build(row):
    """The django.core.mail message for a queued row, with our Message-ID
    (to match bounces) and, for mail people can opt out of, one-click
    unsubscribe headers (RFC 8058)."""
    domain = urlparse(settings.SITE_URL).hostname or "localhost"
    message_id = row.message_id or make_msgid(domain=domain)
    # The envelope sender is the bounce mailbox (with this row's id when it
    # takes plus-addressing), so bounces come back to process_bounces; the
    # From header people see stays DEFAULT_FROM_EMAIL.
    headers = {"Message-ID": message_id, "From": settings.DEFAULT_FROM_EMAIL}
    envelope_from = settings.MAILING_BOUNCE_ADDRESS.replace("{id}", str(row.pk)) or settings.DEFAULT_FROM_EMAIL
    if CAN_OPT_OUT[row.category] and row.user_id:
        headers["List-Unsubscribe"] = f"<{unsubscribe_url(row.user, row.category)}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    message = QueuedEmail(
        subject=row.subject, body=row.body, from_email=envelope_from,
        to=[row.recipient], headers=headers,
    )
    return message, message_id


def _is_permanent(error):
    """A 5xx answer about this one message or recipient: retrying won't
    help. Anything else (down, timeout, 4xx, the sender refused) is the
    server's problem and retried."""
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return all(500 <= code < 600 for code, _msg in error.recipients.values())
    if isinstance(error, smtplib.SMTPSenderRefused):
        return False
    if isinstance(error, smtplib.SMTPResponseException):
        return 500 <= error.smtp_code < 600
    return False


class SendBatchTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # Only after the last retry: whatever is still `sending` failed.
        ids = args[0] if args else kwargs.get("ids", [])
        EmailMessage.objects.filter(pk__in=ids, status=Status.SENDING).update(
            status=Status.FAILED, status_reason=str(exc)[:255],
        )


@shared_task(
    bind=True,
    base=SendBatchTask,
    rate_limit=settings.MAILING_BATCH_RATE_LIMIT,
    autoretry_for=(TransientSendError,),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def send_email_batch(self, ids):
    """Send the rows in `ids` that are still `sending`. Each row is marked
    `sent` right after its own send, so a retried batch never mails anyone
    twice. A permanent error fails only that row."""
    rows = list(EmailMessage.objects.filter(pk__in=ids, status=Status.SENDING).order_by("id"))
    if not rows:
        return 0
    sent = 0
    try:
        with mail.get_connection(fail_silently=False) as connection:
            for row in rows:
                message, message_id = _build(row)
                EmailMessage.objects.filter(pk=row.pk).update(attempts=row.attempts + 1, message_id=message_id)
                try:
                    connection.send_messages([message])
                except (smtplib.SMTPException, OSError) as error:
                    if not _is_permanent(error):
                        raise TransientSendError(str(error)) from error
                    EmailMessage.objects.filter(pk=row.pk).update(status=Status.FAILED, status_reason=str(error)[:255])
                    continue
                EmailMessage.objects.filter(pk=row.pk).update(status=Status.SENT, sent_at=timezone.now(), status_reason="")
                sent += 1
    except (smtplib.SMTPException, OSError) as error:
        # Opening or closing the connection failed.
        raise TransientSendError(str(error)) from error
    return sent


@shared_task
def requeue_stuck_emails():
    """Rows left `sending` for longer than MAILING_CLAIM_TIMEOUT_MINUTES lost
    their subtask (e.g. a Redis flush): put them back in the queue. Such a
    row can go out twice, which beats never sending it. Also logs the
    queue's state, so a stopped worker gets noticed."""
    cutoff = timezone.now() - timedelta(minutes=settings.MAILING_CLAIM_TIMEOUT_MINUTES)
    requeued = EmailMessage.objects.filter(status=Status.SENDING, claimed_at__lt=cutoff).update(
        status=Status.PENDING, claimed_at=None,
    )
    pending = EmailMessage.objects.filter(status=Status.PENDING)
    oldest = pending.aggregate(oldest=Min("created_at"))["oldest"]
    age = (timezone.now() - oldest) if oldest else None
    log = logger.warning if requeued or (age and age > timedelta(minutes=30)) else logger.info
    log("mail queue: %d pending (oldest %s), %d sending, %d requeued", pending.count(),
        f"{int(age.total_seconds() // 60)} min" if age else "none",
        EmailMessage.objects.filter(status=Status.SENDING).count(), requeued)
    return requeued


@shared_task
def process_bounces():
    """Read new bounces and complaints from the bounce mailbox (mailing.bounce).
    Off while MAILING_BOUNCE_IMAP_HOST is empty."""
    if not settings.MAILING_BOUNCE_IMAP_HOST:
        return 0
    from .bounce import BounceProcessor

    return BounceProcessor().process()


@shared_task
def send_session_reminders():
    """Daily: reminders for sessions MAILING_REMINDER_DAYS_BEFORE days ahead."""
    from .automated import send_session_reminders as run

    return run()


@shared_task
def announce_new_sessions():
    """Daily: one "new sessions at your dojo" mail per family and dojo."""
    from .automated import announce_new_sessions as run

    return run()

