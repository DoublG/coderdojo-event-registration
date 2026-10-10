"""The mails the site sends by itself (DATA_MODEL.md §11, phase 5). Each
goes through mailing.services.send(), so consent, the account's language
and the queue apply as for any mail.

A ninja's mail goes to the family: every guardian, plus the ninja's own
login when it has an email address (decided: a child with an account gets
mail about their own bookings).

The views call booking_mail() and waitlist_promoted_mail(); beat runs
send_session_reminders() and announce_new_sessions() daily (mailing.tasks).
A missing template never breaks a sign-up or a cancellation: it's logged
and the mail is skipped.
"""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db.models import QuerySet
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from dojos.models import Dojo
from events.models import Event, Registration

from .categories import MailCategory
from .dojo_families import active_since, family_accounts
from .models import EmailMessage
from .rendering import TemplateMissing
from .services import send

if TYPE_CHECKING:
    from dojos.models import DojoMembership

logger = logging.getLogger(__name__)

Context = dict[str, Any]


def family_of(ninja: Ninja) -> QuerySet[User]:
    """The accounts a ninja's mail goes to: guardians and, with an email,
    the ninja's own login."""
    ids = set(Guardianship.objects.filter(ninja=ninja).values_list("guardian_id", flat=True))
    if ninja.account_id:
        ids.add(ninja.account_id)
    return User.objects.filter(pk__in=ids, is_active=True).exclude(email="").order_by("id")


def _mail_language(user: User) -> str:
    return user.preferred_language or settings.LANGUAGE_CODE


def _session_context(registration: Registration, user: User | None = None) -> Context:
    """The session's details; its name in `user`'s mail language when the
    dojo wrote one (core.content_languages)."""
    event = registration.event
    return {
        "ninja_name": registration.ninja.name,
        "event_name": event.localized("name", _mail_language(user)) if user else event.name,
        "dojo_name": event.dojo.name,
        "start_time": timezone.localtime(event.start_time),
        "end_time": timezone.localtime(event.end_time),
        "venue": event.venue_name or event.dojo.address or event.dojo.name,
        "event_url": settings.SITE_URL + reverse("event_detail", kwargs={"event_id": event.pk}),
        "account_url": settings.SITE_URL + reverse("account_home"),
    }


def _queue(user: User, category: str, template_key: str, context: Context, key: str, dojo: Dojo | None = None) -> int:
    """send() with an idempotency key; returns 1 when this call queued a new
    pending mail (not a repeat, not suppressed), else 0."""
    if EmailMessage.objects.filter(idempotency_key=key).exists():
        return 0
    row = send(user, category, template_key, context, idempotency_key=key, dojo=dojo)
    return int(row.status == EmailMessage.Status.PENDING)


def _send_to_family(
    ninja: Ninja, category: str, template_key: str, context: Context | Callable[[User], Context], key_prefix: str
) -> int:
    """`context` is a dict, or a function of the recipient (for texts in
    their own language)."""
    sent = 0
    for user in family_of(ninja):
        try:
            user_context = context(user) if callable(context) else context
            sent += _queue(user, category, template_key, user_context, f"{key_prefix}:{user.pk}")
        except TemplateMissing:
            logger.exception("mail template %s is missing: nothing sent", template_key)
            return sent
    return sent


def booking_mail(registration: Registration) -> int:
    """Right after a sign-up: a confirmation, or the waiting-list notice."""
    template = "registration_waitlisted" if registration.waiting_list else "registration_confirmed"
    return _send_to_family(
        registration.ninja,
        MailCategory.REGISTRATION,
        template,
        lambda user: _session_context(registration, user),
        f"booking:{registration.pk}",
    )


def waitlist_promoted_mail(registration: Registration) -> int:
    """A place came free and this waitlisted ninja moved up."""
    return _send_to_family(
        registration.ninja,
        MailCategory.REGISTRATION,
        "waitlist_promoted",
        lambda user: _session_context(registration, user),
        f"promoted:{registration.pk}",
    )


def youth_mentor_promoted_mail(membership: "DojoMembership") -> int:
    """A dojo's team made the child a youth mentor: the family is told (no
    approval needed). One mail per promotion, so a re-promotion after
    leaving mails again."""
    ninja = Ninja.objects.filter(account_id=membership.user_id).first()
    if ninja is None:
        return 0
    context = {
        "ninja_name": ninja.name,
        "dojo_name": membership.dojo.name,
        "promoted_by": membership.promoted_by.name if membership.promoted_by else "",
        "ninja_url": settings.SITE_URL + reverse("ninja_detail", kwargs={"ninja_id": ninja.pk}),
    }
    stamp = membership.joined_at.isoformat() if membership.joined_at else ""
    return _send_to_family(
        ninja, MailCategory.SERVICE, "youth_mentor_promoted", context, f"youth_mentor:{membership.pk}:{stamp}"
    )


def send_session_reminders(today: date | None = None) -> int:
    """A reminder for every confirmed place at a session that starts
    MAILING_REMINDER_DAYS_BEFORE days from `today` (Belgian date).
    Idempotent: running it twice on a day sends nothing new."""
    today = today or timezone.localdate()
    day = today + timedelta(days=settings.MAILING_REMINDER_DAYS_BEFORE)
    registrations = (
        Registration.objects.filter(waiting_list=False, event__start_time__date=day)
        .filter(event__in=Event.objects.visible())
        .select_related("event__dojo", "ninja")
    )
    return sum(
        _send_to_family(
            r.ninja,
            MailCategory.REMINDER,
            "session_reminder",
            partial(_session_context, r),
            f"reminder:{r.event_id}:{r.ninja_id}",
        )
        for r in registrations
    )


def announce_new_sessions(now: datetime | None = None) -> int:
    """Tell the families of each dojo about its sessions that opened since
    the last run: one mail per family and dojo, listing them. A family
    belongs to a dojo when a child has it as home dojo or came to one of its
    sessions in the last MAILING_DOJO_NEWS_ACTIVE_DAYS days
    (mailing.dojo_families); a family that muted the dojo doesn't get it. The
    organisation's own events (an organisation dojo, DATA_MODEL.md §12)
    aren't a dojo's news: they reach people through campaigns."""
    now = now or timezone.now()
    new = (
        Event.objects.visible()
        .filter(status=Event.OPEN, announced_at__isnull=True, published_at__isnull=False, start_time__gt=now)
        .exclude(dojo__kind=Dojo.ORGANISATION)
        .order_by("start_time")
    )
    by_dojo: dict[Dojo, list[Event]] = {}
    for event in new:
        by_dojo.setdefault(event.dojo, []).append(event)

    sent = 0
    since = active_since(now)
    for dojo, events in by_dojo.items():
        users = family_accounts(dojo, since)

        def context_for(user: User, dojo: Dojo = dojo, events: list[Event] = events) -> Context:
            return {
                "dojo_name": dojo.name,
                "dojo_url": settings.SITE_URL + reverse("dojo_detail", kwargs={"dojo_id": dojo.pk}),
                "events": [
                    {
                        "name": e.localized("name", _mail_language(user)),
                        "start_time": timezone.localtime(e.start_time),
                        "url": settings.SITE_URL + reverse("event_detail", kwargs={"event_id": e.pk}),
                    }
                    for e in events
                ],
            }

        key = "dojo_news:" + "-".join(str(e.pk) for e in events)
        for user in users:
            try:
                sent += _queue(
                    user,
                    MailCategory.DOJO_NEWS,
                    "new_sessions_at_dojo",
                    context_for(user),
                    f"{key}:{user.pk}",
                    dojo=dojo,
                )
            except TemplateMissing:
                logger.exception("mail template new_sessions_at_dojo is missing: nothing sent")
                return sent
        Event.objects.filter(pk__in=[e.pk for e in events]).update(announced_at=now)
    return sent
