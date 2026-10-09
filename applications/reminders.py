"""Daily background-check mail (DATA_MODEL.md §21), run by applications.tasks.

- The account holder hears 30 days before their check expires, so they can
  ask for a new extract in time (a renewal can only be uploaded once the
  check has lapsed, applications.services).
- Reviewers hear while uploaded documents wait for a decision.

Both are service mail through mailing.services.send_or_log, with an
idempotency key, so a job that runs twice mails nobody twice.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import Permission
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from accounts.models import OrganisationRole, User
from mailing.categories import MailCategory
from mailing.services import send_or_log

REMIND_BEFORE = timedelta(days=30)


def remind_expiring_checks(now: datetime | None = None) -> int:
    """Mail everyone whose check expires within REMIND_BEFORE, once per
    expiry date. Returns how many accounts were due."""
    now = now or timezone.now()
    due = User.objects.filter(
        is_active=True,
        background_check_status=User.CHECK_VALIDATED,
        background_check_expires_at__gt=now,
        background_check_expires_at__lte=now + REMIND_BEFORE,
    )
    account_url = settings.SITE_URL + reverse("account_home")
    for user in due:
        expires_at = timezone.localtime(user.background_check_expires_at)
        send_or_log(
            user,
            MailCategory.SERVICE,
            "background_check_expiring",
            {"expires_at": expires_at, "account_url": account_url},
            idempotency_key=f"background-check-expiring:{user.pk}:{expires_at:%Y-%m-%d}",
        )
    return len(due)


def reviewers() -> QuerySet[User]:
    """The accounts that review background checks: the reviewer role, or the
    permission granted by hand (not every superuser)."""
    permission = Permission.objects.filter(
        content_type__app_label="applications", codename="can_review_background_checks"
    )
    return (
        User.objects.filter(is_active=True, account_type=User.ADULT)
        .exclude(email="")
        .filter(Q(organisation_roles__role=OrganisationRole.REVIEWER) | Q(user_permissions__in=permission))
        .distinct()
    )


def mail_reviewers(now: datetime | None = None) -> int:
    """While documents wait for review, mail each reviewer once a day how
    many (never counting their own). Returns how many reviewers were mailed."""
    day = timezone.localdate(now or timezone.now())
    waiting = User.objects.filter(background_check_status=User.CHECK_SUBMITTED)
    checks_url = settings.SITE_URL + reverse("manage_check_list")
    mailed = 0
    for reviewer in reviewers():
        theirs = waiting.exclude(pk=reviewer.pk)
        count = theirs.count()
        if not count:
            continue
        oldest = theirs.order_by("background_check_submitted_at").values_list(
            "background_check_submitted_at", flat=True
        )[0]
        send_or_log(
            reviewer,
            MailCategory.SERVICE,
            "background_checks_waiting",
            {"count": count, "oldest": timezone.localtime(oldest) if oldest else None, "checks_url": checks_url},
            idempotency_key=f"background-checks-waiting:{reviewer.pk}:{day:%Y-%m-%d}",
        )
        mailed += 1
    return mailed
