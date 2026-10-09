from celery import shared_task

from . import reminders


@shared_task
def remind_expiring_background_checks() -> int:
    """Daily: the 30-day expiry reminder (applications.reminders)."""
    return reminders.remind_expiring_checks()


@shared_task
def mail_background_check_reviewers() -> int:
    """Daily: tell reviewers about documents waiting for review."""
    return reminders.mail_reviewers()
