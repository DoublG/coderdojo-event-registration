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

**Mail content: 12 months** (`MAIL_CONTENT_RETENTION_DAYS`, the `mail_content`
rule). A mail older than that keeps its row, with its category, template,
status and dates, for the statistics, but loses what was personal about it:
the fields its privacy classification marks `personal` (`mailing/privacy.py`:
the account, the address, the subject and body, the idempotency key and the
Message-ID) are emptied. Mail still waiting to be sent is left alone.

**The rules whose period isn't decided yet** are built too, at the end of
this module, and run in the same job once their setting holds a period (None,
the default, is off): a child (`CHILD_RETENTION_DAYS` after their last session
or own login, or at `CHILD_RETENTION_AGE`), rejected applications,
background-check decisions, engagement stage changes, bounce records, read
notifications and the Django admin's log. Two rules have no removal on
purpose: `team` and `team_attendance` (past sessions' teams and the
insurance's record point at them; erasing the person anonymises them), and
`registration` (a registration already points at the anonymised child once the
child is erased). DATA_MODEL.md §16 lists what is still to decide.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import reduce
from operator import or_
from typing import TYPE_CHECKING, Any

from auditlog.models import LogEntry as AuditLogEntry
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Exists, Field, Manager, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext_lazy

from accounts.models import OrganisationRole, User
from core import privacy_registry
from core.privacy_registry import Erasure
from dojos.models import Dojo, DojoMembership
from privacy.erasure import erase_person, sole_children
from privacy.models import ErasureRecord, RetentionNotice

if TYPE_CHECKING:
    from typing import TypedDict

    from django_stubs_ext import WithAnnotations

    from accounts.models import Ninja

    class _InactiveSince(TypedDict):
        inactive_since: datetime

    # A User with with_inactive_since()'s annotation (django-stubs; types only, never imported at run time).
    UserInactiveSince = WithAnnotations[User, _InactiveSince]

logger = logging.getLogger(__name__)

TEMPLATE_KEY = "account_deletion_reminder"
# `days_before` of the notice that the date passed while the account is
# still the champion of an active dojo (no mail, the mentors are notified).
DATE_PASSED = 0
AUDIT_LOG_BATCH = 1000
MAIL_CONTENT_BATCH = 1000


def _first_reminder() -> int:
    return max(settings.ACCOUNT_DELETION_REMINDER_DAYS)


def with_inactive_since(users: QuerySet[User] | Manager[User]) -> "QuerySet[UserInactiveSince]":
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


def inactive_since(user: User) -> datetime:
    since: datetime = (
        with_inactive_since(User.objects.filter(pk=user.pk)).values_list("inactive_since", flat=True).get()
    )
    return since


def is_volunteer(user: User) -> bool:
    """Ever on a dojo's team as champion or mentor: cleaned, not erased."""
    return user.dojo_memberships.filter(role__in=DojoMembership.MANAGER_ROLES, joined_at__isnull=False).exists()


def champion_of_active_dojos(user: User) -> list[Dojo]:
    return list(
        Dojo.objects.filter(
            status=Dojo.ACTIVE,
            memberships__user=user,
            memberships__role=DojoMembership.CHAMPION,
            memberships__status=DojoMembership.ACTIVE,
        ).order_by("name")
    )


def candidates(today: date | None = None) -> "QuerySet[UserInactiveSince]":
    """Accounts the rule applies to whose first reminder is due or past:
    not erased yet, no organisation role, not a superuser, never a ninja's
    own login (it goes with the family) or an API client's technical
    account (it never logs in)."""
    today = today or timezone.localdate()
    # A day's margin for time zones: handle_account decides by the date.
    day = today - timedelta(days=settings.ACCOUNT_RETENTION_DAYS - _first_reminder() - 1)
    # The start of that day in the site's time zone, not a bare date: inactive_since
    # is a timestamp (Django would otherwise make the date a naive midnight).
    cutoff = timezone.make_aware(datetime.combine(day, time.min))
    erased = ErasureRecord.objects.filter(model=User._meta.label, object_id=OuterRef("pk"))
    return (
        with_inactive_since(User.objects)
        .annotate(erased=Exists(erased))
        .filter(inactive_since__lt=cutoff, erased=False, is_superuser=False)
        .exclude(Exists(OrganisationRole.objects.filter(account=OuterRef("pk"))))
        .exclude(account_type__in=[User.NINJA, User.SERVICE])
        .order_by("pk")
    )


@dataclass
class Plan:
    """Where one account stands: its date and the notices it has had."""

    user: User
    since: datetime
    date: date
    notices: dict[int, RetentionNotice]  # days_before -> RetentionNotice

    @property
    def first_sent(self) -> bool:
        return _first_reminder() in self.notices


def plan_for(user: User, today: date | None = None) -> Plan:
    today = today or timezone.localdate()
    since = inactive_since(user)
    notices = {n.days_before: n for n in RetentionNotice.objects.filter(account=user, inactive_since=since)}
    date = timezone.localdate(since) + timedelta(days=settings.ACCOUNT_RETENTION_DAYS)
    first = notices.get(_first_reminder())
    earliest = (timezone.localdate(first.created_at) if first else today) + timedelta(
        days=settings.ACCOUNT_DELETION_NOTICE_DAYS
    )
    return Plan(user, since, max(date, earliest), notices)


def apply_retention(today: date | None = None) -> dict[str, int]:
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
    done["organisation_invitations"] = remove_old_invitations()
    done["mail_content"] = clear_old_mail_content()
    done["sessions"] = Session.objects.filter(expire_date__lt=timezone.now()).delete()[0]
    # The rules waiting for their period: each does nothing while its setting is None.
    done["children"] = erase_old_children(today)
    done["applications"] = remove_old_applications()
    done["background_check_decisions"] = remove_old_background_check_decisions()
    done["engagement_changes"] = remove_old_engagement_changes(today)
    done["bounce_records"] = remove_old_bounce_records()
    done["notifications"] = remove_old_notifications()
    done["admin_log_entries"] = remove_old_admin_log_entries()
    logger.info("retention: %s", done)
    return done


def handle_account(user: User, today: date | None = None) -> str | None:
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


def remind(plan: Plan, days: int) -> None:
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


def reminder_context(plan: Plan) -> dict[str, object]:
    user = plan.user
    context: dict[str, object] = {
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


def _notify_mentors(dojo: Dojo, champion: User, date: date, passed: bool) -> None:
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


def champions_needing_attention(today: date | None = None) -> list[dict[str, Any]]:
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
    rows: list[dict[str, Any]] = []
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


def remove_old_invitations() -> int:
    """Organisation invitations 30 days after they were accepted, withdrawn
    or expired (accounts.invitations, DATA_MODEL.md §23)."""
    from accounts.invitations import remove_old

    return remove_old()


def remove_old_audit_log_entries() -> int:
    """Entries with no account behind them, older than the period, in
    batches. The entries of an account go with its erasure."""
    cutoff = timezone.now() - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
    erased = ErasureRecord.objects.filter(model=User._meta.label).values("object_id")
    old = AuditLogEntry.objects.filter(Q(actor__isnull=True) | Q(actor__in=erased), timestamp__lt=cutoff)
    removed = 0
    while ids := list(old.values_list("pk", flat=True)[:AUDIT_LOG_BATCH]):
        removed += AuditLogEntry.objects.filter(pk__in=ids).delete()[0]
    return removed


# --- mail content --------------------------------------------------------------


def mail_content_values() -> dict[str, str | None]:
    """{column: empty value} for the mail fields the privacy registry marks
    `personal`: what the `mail_content` rule clears. Read from the
    classification, so a personal field added later is cleared too."""
    from mailing.models import EmailMessage

    entry = privacy_registry.get(EmailMessage)
    if entry is None:  # privacy.tests.EveryFieldIsClassifiedTests keeps it classified
        raise LookupError("mailing.EmailMessage has no privacy classification")
    values: dict[str, str | None] = {}
    for name, spec in entry.fields.items():
        if spec.on_erasure != Erasure.DELETE:
            continue
        model_field = EmailMessage._meta.get_field(name)
        if not isinstance(model_field, Field):  # a reverse relation has no column to clear
            continue
        values[model_field.attname] = None if model_field.null else ""
    return values


def clear_old_mail_content(now: datetime | None = None) -> int:
    """Empty the personal fields of mail older than MAIL_CONTENT_RETENTION_DAYS,
    in primary-key ranges of MAIL_CONTENT_BATCH (the table only grows, and its
    ids follow `created_at`). With `QuerySet.update()`, so a batch is one
    statement: the mail log isn't in the audit log, and nothing listens to its
    saves. Returns how many mails were cleared."""
    from mailing.models import EmailMessage

    cutoff = (now or timezone.now()) - timedelta(days=settings.MAIL_CONTENT_RETENTION_DAYS)
    values = mail_content_values()
    has_content = reduce(
        or_,
        (
            Q(**{f"{column}__isnull": False}) if empty is None else ~Q(**{column: empty})
            for column, empty in values.items()
        ),
    )
    old = EmailMessage.objects.filter(created_at__lt=cutoff).exclude(
        status__in=[EmailMessage.Status.PENDING, EmailMessage.Status.SENDING]
    )
    # From the newest end: stops at the first mail past the cutoff.
    last = old.order_by("-pk").values_list("pk", flat=True).first()
    first = old.filter(has_content).order_by("pk").values_list("pk", flat=True).first()
    if last is None or first is None:
        return 0
    cleared = 0
    for start in range(first, last + 1, MAIL_CONTENT_BATCH):
        batch = old.filter(has_content, pk__gte=start, pk__lt=start + MAIL_CONTENT_BATCH)
        cleared += batch.update(**values)
    return cleared


# --- the rules whose period isn't decided yet -----------------------------------------
#
# Each removal is built and runs in the nightly job, but only once its setting
# holds a period; None (the default) leaves the rows alone. DATA_MODEL.md §16,
# "Retention periods, as the code has them", lists the decisions they wait for.
# Applications and background-check decisions are in the audit log: their
# removal runs with it off, or its "deleted" entries would keep what was removed.

_LONG_AGO = timezone.make_aware(datetime(1970, 1, 1))


def _cutoff(days: int, now: datetime | None = None) -> datetime:
    return (now or timezone.now()) - timedelta(days=days)


def children_to_erase(today: date | None = None) -> "QuerySet[Ninja]":
    """Children past `CHILD_RETENTION_DAYS` since their last activity (their
    latest session, upcoming ones included; their own login; or, never having
    done either, since they were added), or aged `CHILD_RETENTION_AGE` or
    more. Never one that's already erased."""
    from django.db.models import Value

    from accounts.models import Guardianship, Ninja
    from events.models import Registration

    days, age = settings.CHILD_RETENTION_DAYS, settings.CHILD_RETENTION_AGE
    if days is None and age is None:
        return Ninja.objects.none()
    today = today or timezone.localdate()
    due = Q()
    if days is not None:
        # Subqueries, not aggregates: one row per child, filtered in WHERE.
        last_session = Registration.objects.filter(ninja=OuterRef("pk")).order_by("-event__start_time")
        first_guardian = Guardianship.objects.filter(ninja=OuterRef("pk")).order_by("created_at")
        own_login = User.objects.filter(pk=OuterRef("account"))
        last_activity = Greatest(
            Coalesce(Subquery(last_session.values("event__start_time")[:1]), Value(_LONG_AGO)),
            Coalesce(Subquery(own_login.values("last_login")[:1]), Value(_LONG_AGO)),
            Coalesce(Subquery(first_guardian.values("created_at")[:1]), Value(_LONG_AGO)),
        )
        due |= Q(last_activity__lt=_cutoff(days))
    if age is not None:
        try:
            born_by = today.replace(year=today.year - age)
        except ValueError:  # 29 February
            born_by = today.replace(year=today.year - age, day=28)
        due |= Q(date_of_birth__lte=born_by)
    erased = ErasureRecord.objects.filter(model=Ninja._meta.label, object_id=OuterRef("pk"))
    children = Ninja.objects.alias(erased=Exists(erased))
    if days is not None:
        children = children.alias(last_activity=last_activity)
    return children.filter(due, erased=False)


def erase_old_children(today: date | None = None) -> int:
    """The `child` rule: erase each child it's due for, with their own login
    (privacy.erasure.erase_child), one transaction each. Returns how many."""
    from privacy.erasure import erase_child

    erased = 0
    for ninja in list(children_to_erase(today)):
        try:
            erase_child(ninja, reason=ErasureRecord.RETENTION)
        except Exception:
            logger.exception("retention: child %s failed", ninja.pk)
            continue
        erased += 1
    return erased


def remove_old_applications() -> int:
    """The `application` rule: rejected applications `APPLICATION_RETENTION_DAYS`
    after the decision. An approved one stays while the account does: it's what
    makes them a mentor or champion."""
    from auditlog.context import disable_auditlog

    from applications.models import Application

    if settings.APPLICATION_RETENTION_DAYS is None:
        return 0
    with disable_auditlog():
        return Application.objects.filter(
            status=Application.REJECTED, decided_at__lt=_cutoff(settings.APPLICATION_RETENTION_DAYS)
        ).delete()[0]


def remove_old_background_check_decisions() -> int:
    """The `background_check` rule for the decisions (the document itself is
    gone at the decision): `BackgroundCheckHistory` rows
    `BACKGROUND_CHECK_HISTORY_RETENTION_DAYS` after they were made. Access never
    depends on them: a check's validity is on the account."""
    from auditlog.context import disable_auditlog

    from applications.models import BackgroundCheckHistory

    if settings.BACKGROUND_CHECK_HISTORY_RETENTION_DAYS is None:
        return 0
    with disable_auditlog():
        return BackgroundCheckHistory.objects.filter(
            reviewed_at__lt=_cutoff(settings.BACKGROUND_CHECK_HISTORY_RETENTION_DAYS)
        ).delete()[0]


def remove_old_engagement_changes(today: date | None = None) -> int:
    """The `engagement` rule for stage changes: `NinjaEngagementChange` rows
    `ENGAGEMENT_CHANGE_RETENTION_DAYS` after the day they happened. A segment's
    `stage_changed` rule can't look back further than that."""
    from events.models import NinjaEngagementChange

    if settings.ENGAGEMENT_CHANGE_RETENTION_DAYS is None:
        return 0
    since = (today or timezone.localdate()) - timedelta(days=settings.ENGAGEMENT_CHANGE_RETENTION_DAYS)
    return NinjaEngagementChange.objects.filter(changed_on__lt=since).delete()[0]


def remove_old_bounce_records() -> int:
    """The `mail_log` rule: `BounceRecord`s `BOUNCE_RECORD_RETENTION_DAYS` after
    they were read, never sooner than the soft-bounce window they're counted in.
    The handled-mailbox rows (`ProcessedImapMessage`) stay: they hold nothing
    personal, and they stop a message still in the mailbox being read twice."""
    from mailing.models import BounceRecord

    if settings.BOUNCE_RECORD_RETENTION_DAYS is None:
        return 0
    days = max(settings.BOUNCE_RECORD_RETENTION_DAYS, settings.MAILING_SOFT_BOUNCE_WINDOW_DAYS)
    return BounceRecord.objects.filter(created_at__lt=_cutoff(days)).delete()[0]


def remove_old_notifications() -> int:
    """The `notification` rule: notifications that were read,
    `NOTIFICATION_RETENTION_DAYS` after they were made. Unread ones stay."""
    from notifications.models import Notification

    if settings.NOTIFICATION_RETENTION_DAYS is None:
        return 0
    return Notification.objects.filter(
        read=True, created_at__lt=_cutoff(settings.NOTIFICATION_RETENTION_DAYS)
    ).delete()[0]


def remove_old_admin_log_entries() -> int:
    """The `admin_log` rule: the Django admin's own log of changes made by hand,
    `ADMIN_LOG_RETENTION_DAYS` after the change. The audit log has its own rule."""
    from django.contrib.admin.models import LogEntry

    if settings.ADMIN_LOG_RETENTION_DAYS is None:
        return 0
    return LogEntry.objects.filter(action_time__lt=_cutoff(settings.ADMIN_LOG_RETENTION_DAYS)).delete()[0]
