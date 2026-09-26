"""Retention: deleting what's no longer needed (DATA_MODEL.md §16 phase 4).
Run every night by `privacy.tasks.apply_retention`; safe to run twice.

**Accounts: two years after the last login** (`ACCOUNT_RETENTION_DAYS`,
`User.last_login`, or `date_joined` for an account that never logged in).
A guardian's account counts its children's own logins too: a family is in
use while a child logs in. Only logging in moves the date on. First the
account gets the reminder mails (`ACCOUNT_DELETION_REMINDER_DAYS`, 30 and 7
days before; the service mail `account_deletion_reminder`), then, on the
date:

- a family's account is erased (`privacy.erasure.erase_person`), with the
  children only it is a guardian of and their own logins;
- a champion's or mentor's account (a membership that ever got past
  `requested`) is cleaned: erased with `keep_visible`, so their name stays
  on past sessions and their team profile if it was shown. While they're
  still the champion of an active dojo nothing happens: the organisation
  sees them under "Needs attention" on its Privacy page, and the dojo's
  mentors are notified at the first reminder and when the date has passed.

A child's own login has no date of its own: it's on its guardians'
counter, their reminders are the notice it goes, and it's erased with its
child. The job never handles a ninja login itself; one whose child has no
guardian can only come from a manual fix in the Django admin, and stays
until it's handled there.

The date is never earlier than `ACCOUNT_DELETION_NOTICE_DAYS` (30) after the
first reminder, so nobody is deleted without a month's notice (an account
that was already overdue when the rule started, or whose organisation role
just ended). Accounts holding an organisation role, and superusers, are
left alone for as long as they are. Each reminder is a `RetentionNotice`;
a login starts a new period, with new reminders.

**The audit log** (§14): an account's entries go with its erasure; entries
with no account behind them (a background job, a command, or an erased
account) are removed `AUDIT_LOG_RETENTION_DAYS` after they were written.

**Login sessions** are removed once they've expired.

The other rules in `privacy.registry.RETENTION_RULES` still wait for their
periods (DATA_MODEL.md §16, open points).
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from auditlog.models import LogEntry as AuditLogEntry
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext_lazy

from accounts.models import OrganisationRole, User
from dojos.models import Dojo, DojoMembership
from privacy.erasure import erase_person, sole_children
from privacy.models import ErasureRecord, RetentionNotice

logger = logging.getLogger(__name__)

TEMPLATE_KEY = "account_deletion_reminder"
# `days_before` of the notice that the date passed while the account is
# still the champion of an active dojo (no mail, the mentors are notified).
DATE_PASSED = 0
AUDIT_LOG_BATCH = 1000


def _first_reminder():
    return max(settings.ACCOUNT_DELETION_REMINDER_DAYS)


def with_inactive_since(users):
    """Annotate `inactive_since` on a User queryset: the last login (or
    `date_joined`, never logged in), or a later login of one of the
    account's children's own logins."""
    own = Coalesce("last_login", "date_joined")
    child_login = (
        User.objects.filter(ninja__guardianships__guardian=OuterRef("pk"), last_login__isnull=False)
        .order_by("-last_login")
        .values("last_login")[:1]
    )
    return users.annotate(inactive_since=Greatest(own, Coalesce(Subquery(child_login), own)))


def inactive_since(user):
    return with_inactive_since(User.objects.filter(pk=user.pk)).values_list("inactive_since", flat=True).get()


def is_volunteer(user):
    """Ever on a dojo's team as champion or mentor: cleaned, not erased."""
    return user.dojo_memberships.filter(role__in=DojoMembership.MANAGER_ROLES, joined_at__isnull=False).exists()


def champion_of_active_dojos(user):
    return list(
        Dojo.objects.filter(
            status=Dojo.ACTIVE,
            memberships__user=user,
            memberships__role=DojoMembership.CHAMPION,
            memberships__status=DojoMembership.ACTIVE,
        ).order_by("name")
    )


def candidates(today=None):
    """Accounts the rule applies to whose first reminder is due or past:
    not erased yet, no organisation role, not a superuser, never a ninja's
    own login (it goes with the family)."""
    today = today or timezone.localdate()
    # A day's margin for time zones: handle_account decides by the date.
    cutoff = today - timedelta(days=settings.ACCOUNT_RETENTION_DAYS - _first_reminder() - 1)
    erased = ErasureRecord.objects.filter(model=User._meta.label, object_id=OuterRef("pk"))
    return (
        with_inactive_since(User.objects)
        .annotate(erased=Exists(erased))
        .filter(inactive_since__lt=cutoff, erased=False, is_superuser=False)
        .exclude(Exists(OrganisationRole.objects.filter(account=OuterRef("pk"))))
        .exclude(account_type=User.NINJA)
        .order_by("pk")
    )


@dataclass
class Plan:
    """Where one account stands: its date and the notices it has had."""

    user: User
    since: object
    date: object
    notices: dict  # days_before -> RetentionNotice

    @property
    def first_sent(self):
        return _first_reminder() in self.notices


def plan_for(user, today=None):
    today = today or timezone.localdate()
    since = inactive_since(user)
    notices = {n.days_before: n for n in RetentionNotice.objects.filter(account=user, inactive_since=since)}
    date = timezone.localdate(since) + timedelta(days=settings.ACCOUNT_RETENTION_DAYS)
    first = notices.get(_first_reminder())
    earliest = (timezone.localdate(first.created_at) if first else today) + timedelta(
        days=settings.ACCOUNT_DELETION_NOTICE_DAYS
    )
    return Plan(user, since, max(date, earliest), notices)


def apply_retention(today=None):
    """The nightly job: reminders, deletions, the audit log and sessions.
    One account's failure is logged and never stops the rest."""
    today = today or timezone.localdate()
    # Reminders about a period a login has since ended.
    current = with_inactive_since(User.objects.filter(pk=OuterRef("account"))).values("inactive_since")[:1]
    RetentionNotice.objects.exclude(inactive_since=Subquery(current)).delete()
    done = {"reminders": 0, "erased": 0, "cleaned": 0, "held_back": 0, "failed": 0}
    for user in candidates(today):
        try:
            with transaction.atomic():
                outcome = handle_account(user, today)
        except Exception:
            logger.exception("retention: account %s failed", user.pk)
            done["failed"] += 1
            continue
        if outcome:
            done[outcome] += 1
    done["audit_log_entries"] = remove_old_audit_log_entries()
    done["sessions"] = Session.objects.filter(expire_date__lt=timezone.now()).delete()[0]
    logger.info("retention: %s", done)
    return done


def handle_account(user, today=None):
    """Send the reminder that's due, or apply the rule once the date has
    passed. Returns what happened (a key of `apply_retention`'s result) or
    None."""
    today = today or timezone.localdate()
    plan = plan_for(user, today)
    for days in sorted(settings.ACCOUNT_DELETION_REMINDER_DAYS, reverse=True):
        if days in plan.notices:
            continue
        if today >= plan.date - timedelta(days=days):
            remind(plan, days)
            return "reminders"
        return None
    if today < plan.date:
        return None
    if dojos := champion_of_active_dojos(user):
        if DATE_PASSED not in plan.notices:
            RetentionNotice.objects.create(account=user, inactive_since=plan.since, days_before=DATE_PASSED)
            for dojo in dojos:
                _notify_mentors(dojo, user, plan.date, passed=True)
        return "held_back"
    if is_volunteer(user):
        erase_person(user, reason=ErasureRecord.RETENTION, keep_visible=True)
        return "cleaned"
    erase_person(user, reason=ErasureRecord.RETENTION)
    return "erased"


# --- reminders ---------------------------------------------------------------


def remind(plan, days):
    """Mail reminder `days` and record it. The mail is `service` mail, so it
    can't be switched off; a blocked address or an account without one is
    recorded as suppressed by send(), and the date stands."""
    from mailing.categories import MailCategory
    from mailing.services import send

    user = plan.user
    RetentionNotice.objects.create(account=user, inactive_since=plan.since, days_before=days)
    # The first reminder moves the date to a month from now at the earliest.
    plan = plan_for(user)
    key = f"account-deletion:{user.pk}:{days}:{timezone.localdate(plan.since):%Y-%m-%d}"
    context = reminder_context(plan)
    send(user, MailCategory.SERVICE, TEMPLATE_KEY, context, idempotency_key=key)
    if days == _first_reminder():
        for dojo in champion_of_active_dojos(user):
            _notify_mentors(dojo, user, plan.date, passed=False)


def reminder_context(plan):
    user = plan.user
    context = {
        "deletion_date": plan.date,
        "login_url": settings.SITE_URL + reverse("login"),
    }
    volunteer = is_volunteer(user)
    context.update(
        children=[child.name for child in sole_children(user)],
        volunteer=volunteer,
        keeps_profile=volunteer and user.show_on_team_pages,
        champion_of=[dojo.name for dojo in champion_of_active_dojos(user)],
    )
    return context


def _notify_mentors(dojo, champion, date, passed):
    """The dojo's other managers, on the dashboard bell: the champion
    can't be cleaned while the dojo depends on them."""
    from dojos.team import notify_managers

    if passed:
        text = gettext_lazy(
            "%(name)s, the champion of %(dojo)s, hasn't logged in for two years. Their account was due to be "
            "cleaned on %(date)s, but can't be while they're the champion. Ask them to hand the role to a mentor, "
            "or contact the organisation."
        )
    else:
        text = gettext_lazy(
            "%(name)s, the champion of %(dojo)s, hasn't logged in for two years. Their account will be cleaned "
            "on %(date)s, but not while they're the champion. Ask them to hand the role to a mentor, or contact "
            "the organisation."
        )
    notify_managers(
        dojo,
        text,
        url=reverse("dojo_team_manage", kwargs={"dojo_id": dojo.id}),
        exclude=champion,
        params={"name": champion.team_name, "dojo": dojo.name, "date": formats.date_format(date, "d/m/Y")},
    )


# --- the organisation's list -----------------------------------------------


def champions_needing_attention(today=None):
    """Champions of an active dojo who got their first reminder: they can't
    be cleaned until the role moves. One row per dojo, soonest date first."""
    today = today or timezone.localdate()
    memberships = (
        DojoMembership.objects.filter(
            role=DojoMembership.CHAMPION,
            status=DojoMembership.ACTIVE,
            dojo__status=Dojo.ACTIVE,
            user__retention_notices__days_before=_first_reminder(),
        )
        .exclude(Q(user__is_superuser=True) | Q(user__organisation_roles__isnull=False))
        .select_related("dojo", "user")
        .distinct()
    )
    rows = []
    for membership in memberships:
        plan = plan_for(membership.user, today)
        if plan.first_sent:  # about the current period, not one a login ended
            rows.append(
                {
                    "dojo": membership.dojo,
                    "champion": membership.user,
                    "last_login": membership.user.last_login,
                    "date": plan.date,
                    "passed": today >= plan.date,
                }
            )
    return sorted(rows, key=lambda row: (row["date"], row["dojo"].name))


# --- the audit log -----------------------------------------------------------


def remove_old_audit_log_entries():
    """Entries with no account behind them, older than the period, in
    batches. The entries of an account go with its erasure."""
    cutoff = timezone.now() - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
    erased = ErasureRecord.objects.filter(model=User._meta.label).values("object_id")
    old = AuditLogEntry.objects.filter(Q(actor__isnull=True) | Q(actor__in=erased), timestamp__lt=cutoff)
    removed = 0
    while ids := list(old.values_list("pk", flat=True)[:AUDIT_LOG_BATCH]):
        removed += AuditLogEntry.objects.filter(pk__in=ids).delete()[0]
    return removed
