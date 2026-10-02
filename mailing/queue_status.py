"""Whether mail is going out: shared by the organisation's Mail queue
(mailing.manage.mail_queue) and a dojo's (mailing.dojo_views.dojo_mail_queue)."""

from datetime import timedelta

from django.db.models import Min, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import EmailMessage

# Mail due longer than this and still waiting means the workers aren't sending
# (the same threshold as requeue_stuck_emails' warning in the log).
STALLED_AFTER = timedelta(minutes=30)


def due_q(now=None):
    now = now or timezone.now()
    return Q(send_after__isnull=True) | Q(send_after__lte=now)


def oldest_due(now=None):
    """When the longest-waiting due mail (any mail, anyone's) was due, or None."""
    return (
        EmailMessage.objects.filter(due_q(now), status=EmailMessage.Status.PENDING)
        .annotate(due_at=Coalesce("send_after", "created_at"))
        .aggregate(oldest=Min("due_at"))["oldest"]
    )


def snapshot(now=None):
    """Mail waiting to be sent, and how long the oldest due one has waited:
    what /metrics/ shows (registered with monitoring.collect)."""
    now = now or timezone.now()
    oldest = oldest_due(now)
    return {
        "pending": EmailMessage.objects.filter(status=EmailMessage.Status.PENDING).count(),
        "sending": EmailMessage.objects.filter(status=EmailMessage.Status.SENDING).count(),
        "oldest_due_seconds": int((now - oldest).total_seconds()) if oldest else 0,
    }


def is_stalled(oldest, now=None):
    return bool(oldest and (now or timezone.now()) - oldest > STALLED_AFTER)
