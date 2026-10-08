"""Fixing the mail queue from the organisation dashboard: sending a failed
mail again, and blocking or unblocking an address. The Mail queue and Mail log pages
(mailing.manage) only call these; MailQueueError carries a message for the
person who clicked.

Sending again puts the same row back in the queue, so the row stays the
record of exactly what was sent: the worker checks the account's consent and
the address's block again right before it goes out (tasks.send_email_batch),
as for any mail. Blocking by hand adds an EmailSuppression ("Blocked by hand")
and withdraws the mail still waiting for that address; unblocking deletes it.
Blocking a domain (BlockedDomain) works the same for every address in it
and its subdomains. The audit log records all of these; none touches the person's own mail choices (a
complaint switched those off through mailing.preferences)."""

from django.db.models import Q, QuerySet
from django.utils.translation import gettext as _

from .models import BlockedDomain, EmailMessage, EmailSuppression
from .services import BLOCKED, is_suppressed_address


class MailQueueError(Exception):
    """Why a mail can't be sent again, in words for the dashboard."""


def retry_problem(message: EmailMessage) -> str | None:
    """Why `message` can't be sent again, or None when it can."""
    if message.status != EmailMessage.Status.FAILED:
        return _("Only a mail that failed can be sent again.")
    if not message.recipient or not message.body:
        # privacy.retention.clear_old_mail_content emptied it.
        return _("This mail's content was cleared after a year, so it can't be sent again.")
    if is_suppressed_address(message.recipient):
        return _("%(email)s is blocked. Unblock the address first if the mail should go there.") % {
            "email": message.recipient
        }
    return None


def retry(message: EmailMessage) -> None:
    """Put a failed mail back in the queue, to go out with the next round."""
    if problem := retry_problem(message):
        raise MailQueueError(problem)
    # Only if it's still failed: a second click, or two people at once.
    updated = EmailMessage.objects.filter(pk=message.pk, status=EmailMessage.Status.FAILED).update(
        status=EmailMessage.Status.PENDING,
        status_reason="",
        attempts=0,
        claimed_at=None,
        send_after=None,
    )
    if not updated:
        raise MailQueueError(_("Only a mail that failed can be sent again."))


def retry_failed(messages: QuerySet[EmailMessage]) -> tuple[int, int]:
    """Send every failed mail in `messages` (a queryset) again that can be.
    Returns (sent again, skipped); a skipped one is blocked or cleared."""
    retried = skipped = 0
    for message in messages.filter(status=EmailMessage.Status.FAILED).order_by("pk"):
        try:
            retry(message)
        except MailQueueError:
            skipped += 1
        else:
            retried += 1
    return retried, skipped


def block(email: str, note: str = "") -> tuple[EmailSuppression, int]:
    """Stop all mail to `email`, whatever the person chose: an EmailSuppression
    "Blocked by hand", created with save() so the audit log records who. Mail
    still waiting for the address is withdrawn here (the worker only checks the
    block again for mail to an account). Returns (the block, how many mails
    were withdrawn)."""
    email = email.strip().lower()
    if is_suppressed_address(email):
        raise MailQueueError(_("%(email)s is already blocked.") % {"email": email})
    suppression = EmailSuppression.objects.create(email=email, reason=EmailSuppression.MANUAL, note=note.strip())
    withdrawn = EmailMessage.objects.filter(recipient__iexact=email, status=EmailMessage.Status.PENDING).update(
        status=EmailMessage.Status.SUPPRESSED, status_reason=BLOCKED
    )
    return suppression, withdrawn


def unblock(suppression: EmailSuppression) -> str:
    """Let mail go to the address again. Returns the address."""
    email = suppression.email
    suppression.delete()  # delete(), not a queryset: the audit log records who did it
    return email


def block_domain(domain: str, note: str = "") -> tuple[BlockedDomain, int]:
    """Stop all mail to every address in `domain` and its subdomains (made-up
    demo addresses, a domain that must never be mailed), created with save()
    so the audit log records who. Mail still waiting for such an address is
    withdrawn here. Returns (the block, how many mails were withdrawn)."""
    domain = domain.strip().lower().lstrip("@").removeprefix("*.").strip(".")
    if BlockedDomain.objects.filter(domain=domain).exists():
        raise MailQueueError(_("%(domain)s is already blocked.") % {"domain": domain})
    blocked = BlockedDomain.objects.create(domain=domain, note=note.strip())
    withdrawn = (
        EmailMessage.objects.filter(status=EmailMessage.Status.PENDING)
        .filter(Q(recipient__iendswith=f"@{domain}") | Q(recipient__iendswith=f".{domain}"))
        .update(status=EmailMessage.Status.SUPPRESSED, status_reason=BLOCKED)
    )
    return blocked, withdrawn


def unblock_domain(blocked: BlockedDomain) -> str:
    """Let mail go to the domain again (addresses blocked one by one stay
    blocked). Returns the domain."""
    domain = blocked.domain
    blocked.delete()  # delete(), not a queryset: the audit log records who did it
    return domain
