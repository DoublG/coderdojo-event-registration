"""The mail queue, read-only: mail waiting and failed, bounces and blocked
addresses; retrying and unblocking stay in the Django admin."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from accounts.organisation import Area, require_area

from .. import queue_status
from ..models import BounceRecord, EmailMessage, EmailSuppression

# --- the mail queue: what's waiting, what failed, bounces and blocked addresses ---

MAIL_QUEUE_LIMIT = 50  # rows per section


MAIL_QUEUE_RECENT_DAYS = 30  # how far back failures and bounces are shown


@login_required
def mail_queue(request):
    """The mail queue at a glance (read-only): mail waiting to go out, mail
    that failed, bounces and complaints read from the bounce mailbox, and
    the addresses nothing is sent to any more. Fixing things (retrying a
    mail, unblocking an address) stays in the Django admin."""
    require_area(request, Area.COMMUNICATION)
    now = timezone.now()
    since = now - timedelta(days=MAIL_QUEUE_RECENT_DAYS)
    Status = EmailMessage.Status
    query = request.GET.get("q", "").strip()

    mail = EmailMessage.objects.select_related("campaign")
    bounces = BounceRecord.objects.select_related("message")
    blocked = EmailSuppression.objects.all()
    if query:
        mail = mail.filter(Q(recipient__icontains=query) | Q(user__email__icontains=query))
        bounces = bounces.filter(email__icontains=query)
        blocked = blocked.filter(email__icontains=query)

    due = queue_status.due_q(now)
    oldest_due = queue_status.oldest_due(now)
    waiting = mail.filter(status__in=[Status.PENDING, Status.SENDING])
    failed = mail.filter(status=Status.FAILED, created_at__gte=since)
    recent_bounces = bounces.filter(created_at__gte=since)
    counts = {
        "pending": EmailMessage.objects.filter(due, status=Status.PENDING).count(),
        "scheduled": EmailMessage.objects.filter(status=Status.PENDING, send_after__gt=now).count(),
        "sending": EmailMessage.objects.filter(status=Status.SENDING).count(),
        "sent_today": EmailMessage.objects.filter(status=Status.SENT, sent_at__gte=now - timedelta(days=1)).count(),
        "failed": EmailMessage.objects.filter(status=Status.FAILED, created_at__gte=since).count(),
        "bounces": BounceRecord.objects.filter(created_at__gte=since).count(),
        "blocked": EmailSuppression.objects.count(),
    }
    return render(
        request,
        "mailing/manage/mail_queue.html",
        {
            "active": "mail_queue",
            "query": query,
            "counts": counts,
            "recent_days": MAIL_QUEUE_RECENT_DAYS,
            "limit": MAIL_QUEUE_LIMIT,
            "oldest_due": oldest_due,
            "stalled": queue_status.is_stalled(oldest_due, now),
            "bounce_mailbox_on": bool(settings.MAILING_BOUNCE_IMAP_HOST),
            "waiting": waiting.order_by("priority", "created_at")[:MAIL_QUEUE_LIMIT],
            "failed": failed.order_by("-created_at")[:MAIL_QUEUE_LIMIT],
            "bounces": recent_bounces[:MAIL_QUEUE_LIMIT],
            "blocked": blocked.order_by("-created_at")[:MAIL_QUEUE_LIMIT],
        },
    )
