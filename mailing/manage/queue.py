"""The mail queue and the mail log: mail waiting and failed, bounces and
blocked addresses, and every mail sent. Sending a failed mail again and
unblocking an address are buttons here, through mailing.queue_actions; a
mail's text stays in the Django admin (a login or password-reset mail holds
a working link)."""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.http import require_POST

from accounts.organisation import Area, require_area

from .. import queue_status, services
from ..categories import MailCategory
from ..models import BounceRecord, EmailMessage, EmailSuppression
from ..queue_actions import MailQueueError, retry, retry_failed, unblock

# --- the mail queue: what's waiting, what failed, bounces and blocked addresses ---

MAIL_QUEUE_LIMIT = 50  # rows per section


MAIL_QUEUE_RECENT_DAYS = 30  # how far back failures and bounces are shown


@login_required
def mail_queue(request):
    """The mail queue at a glance: mail waiting to go out, mail that failed
    (with Send again), bounces and complaints read from the bounce mailbox,
    and the addresses nothing is sent to any more (with Unblock)."""
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


# --- the mail log: every mail, newest first ---------------------------------------

MAIL_LOG_PAGE_SIZE = 50

# EmailMessage.status_reason of mail that wasn't sent, in words. Anything else
# (a mail server's answer, a bounce) is shown as it is.
NOT_SENT_REASONS = {
    services.INACTIVE: gettext_lazy("The account is switched off."),
    services.WRONG_ACCOUNT_TYPE: gettext_lazy("This kind of mail doesn't go to this kind of account."),
    services.NOT_SUBSCRIBED: gettext_lazy("The person switched off this kind of mail."),
    services.MUTED_DOJO: gettext_lazy("The family stopped this dojo's news."),
    services.NO_ADDRESS: gettext_lazy("The account has no email address."),
    services.BLOCKED: gettext_lazy("The address is blocked (a bounce, a spam complaint or by hand)."),
    # campaigns.services.CANCELLED (mailing doesn't import campaigns; a test keeps them equal)
    "The campaign was cancelled.": gettext_lazy("The campaign was cancelled before it went out."),
}


@login_required
def mail_log(request):
    """Every mail the site queued, newest first, filtered by address or
    subject, status and kind of mail: to answer "did they get it?" and to
    send a failed one again. Never the text (see the module docstring)."""
    require_area(request, Area.COMMUNICATION)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    category = request.GET.get("category", "")
    mail = EmailMessage.objects.select_related("campaign").order_by("-created_at", "-pk")
    if query:
        mail = mail.filter(
            Q(recipient__icontains=query) | Q(user__email__icontains=query) | Q(subject__icontains=query)
        )
    if status in EmailMessage.Status.values:
        mail = mail.filter(status=status)
    else:
        status = ""
    if category in MailCategory.values:
        mail = mail.filter(category=category)
    else:
        category = ""
    page = Paginator(mail, MAIL_LOG_PAGE_SIZE).get_page(request.GET.get("page"))
    for message in page.object_list:
        message.reason_text = NOT_SENT_REASONS.get(message.status_reason, message.status_reason)
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "mailing/manage/mail_log.html",
        {
            "active": "mail_log",
            "page": page,
            "filter_query": params.urlencode(),
            "query": query,
            "status": status,
            "statuses": EmailMessage.Status.choices,
            "category": category,
            "categories": MailCategory.choices,
            "blocked": set(
                EmailSuppression.objects.filter(
                    email__in={m.recipient.lower() for m in page.object_list if m.recipient}
                ).values_list("email", flat=True)
            ),
        },
    )


# --- fixing things: send a failed mail again, unblock an address ------------------


def _back(request, default="manage_mail_queue"):
    """Back to the page the button was on (its `next`), else `default`."""
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect(default)


@login_required
@require_POST
def mail_retry(request, message_id):
    require_area(request, Area.COMMUNICATION)
    message = get_object_or_404(EmailMessage, pk=message_id)
    try:
        retry(message)
    except MailQueueError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            _("The mail to %(email)s is back in the queue and goes out within a minute or so.")
            % {"email": message.recipient},
        )
    return _back(request)


@login_required
@require_POST
def mail_retry_failed(request):
    """Send the Mail queue's failed mail again: the last
    MAIL_QUEUE_RECENT_DAYS, for one address when the page was searched."""
    require_area(request, Area.COMMUNICATION)
    failed = EmailMessage.objects.filter(created_at__gte=timezone.now() - timedelta(days=MAIL_QUEUE_RECENT_DAYS))
    if query := request.POST.get("q", "").strip():
        failed = failed.filter(Q(recipient__icontains=query) | Q(user__email__icontains=query))
    retried, skipped = retry_failed(failed)
    if retried:
        messages.success(
            request,
            ngettext("%(count)d mail is back in the queue.", "%(count)d mails are back in the queue.", retried)
            % {"count": retried},
        )
    if skipped:
        messages.warning(
            request,
            ngettext(
                "%(count)d mail wasn't sent again: its address is blocked, or its content was cleared.",
                "%(count)d mails weren't sent again: their address is blocked, or their content was cleared.",
                skipped,
            )
            % {"count": skipped},
        )
    if not retried and not skipped:
        messages.info(request, _("There's no failed mail to send again."))
    return _back(request)


@login_required
@require_POST
def mail_unblock(request, suppression_id):
    require_area(request, Area.COMMUNICATION)
    email = unblock(get_object_or_404(EmailSuppression, pk=suppression_id))
    messages.success(
        request,
        _("%(email)s is unblocked: mail goes there again. The person's own mail choices haven't changed.")
        % {"email": email},
    )
    return _back(request)
