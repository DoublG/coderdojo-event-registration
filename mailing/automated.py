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
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from dojos.models import Dojo
from events.models import Event, Registration

from .categories import MailCategory
from .models import EmailMessage
from .rendering import TemplateMissing
from .services import send

logger = logging.getLogger(__name__)


def family_of(ninja):
    """The accounts a ninja's mail goes to: guardians and, with an email,
    the ninja's own login."""
    ids = set(Guardianship.objects.filter(ninja=ninja).values_list("guardian_id", flat=True))
    if ninja.account_id:
        ids.add(ninja.account_id)
    return User.objects.filter(pk__in=ids, is_active=True).exclude(email="").order_by("id")


def _session_context(registration):
    event = registration.event
    return {
        "ninja_name": registration.ninja.name.split()[0],
        "event_name": event.name,
        "dojo_name": event.dojo.name,
        "start_time": timezone.localtime(event.start_time),
        "end_time": timezone.localtime(event.end_time),
        "venue": event.venue_name or event.dojo.address or event.dojo.name,
        "event_url": settings.SITE_URL + reverse("event_detail", kwargs={"event_id": event.pk}),
        "account_url": settings.SITE_URL + reverse("account_home"),
    }


def _queue(user, category, template_key, context, key):
    """send() with an idempotency key; returns 1 when this call queued a new
    pending mail (not a repeat, not suppressed), else 0."""
    if EmailMessage.objects.filter(idempotency_key=key).exists():
        return 0
    row = send(user, category, template_key, context, idempotency_key=key)
    return int(row.status == EmailMessage.Status.PENDING)


def _send_to_family(ninja, category, template_key, context, key_prefix):
    sent = 0
    for user in family_of(ninja):
        try:
            sent += _queue(user, category, template_key, context, f"{key_prefix}:{user.pk}")
        except TemplateMissing:
            logger.exception("mail template %s is missing: nothing sent", template_key)
            return sent
    return sent


def booking_mail(registration):
    """Right after a sign-up: a confirmation, or the waiting-list notice."""
    template = "registration_waitlisted" if registration.waiting_list else "registration_confirmed"
    return _send_to_family(registration.ninja, MailCategory.REGISTRATION, template, _session_context(registration),
                           f"booking:{registration.pk}")


def waitlist_promoted_mail(registration):
    """A place came free and this waitlisted ninja moved up."""
    return _send_to_family(registration.ninja, MailCategory.REGISTRATION, "waitlist_promoted",
                           _session_context(registration), f"promoted:{registration.pk}")


def youth_mentor_promoted_mail(membership):
    """A dojo's team made the child a youth mentor: the family is told (no
    approval needed). One mail per promotion, so a re-promotion after
    leaving mails again."""
    ninja = Ninja.objects.filter(account_id=membership.user_id).first()
    if ninja is None:
        return 0
    context = {
        "ninja_name": ninja.name.split()[0],
        "dojo_name": membership.dojo.name,
        "promoted_by": membership.promoted_by.name if membership.promoted_by_id else "",
        "ninja_url": settings.SITE_URL + reverse("ninja_detail", kwargs={"ninja_id": ninja.pk}),
    }
    stamp = membership.joined_at.isoformat() if membership.joined_at else ""
    return _send_to_family(ninja, MailCategory.SERVICE, "youth_mentor_promoted", context,
                           f"youth_mentor:{membership.pk}:{stamp}")


def send_session_reminders(today=None):
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
        _send_to_family(r.ninja, MailCategory.REMINDER, "session_reminder", _session_context(r),
                        f"reminder:{r.event_id}:{r.ninja_id}")
        for r in registrations
    )


def announce_new_sessions(now=None):
    """Tell the families of each dojo about its sessions that opened since
    the last run: one mail per family and dojo, listing them. A family
    belongs to a dojo when a child has it as home dojo or came to one of its
    sessions in the last MAILING_DOJO_NEWS_ACTIVE_DAYS days. The
    organisation's own events (an organisation dojo, DATA_MODEL.md §12)
    aren't a dojo's news: they reach people through campaigns."""
    now = now or timezone.now()
    new = (
        Event.objects.visible()
        .filter(status=Event.OPEN, announced_at__isnull=True, published_at__isnull=False, start_time__gt=now)
        .exclude(dojo__kind=Dojo.ORGANISATION)
        .order_by("start_time")
    )
    by_dojo = {}
    for event in new:
        by_dojo.setdefault(event.dojo, []).append(event)

    sent = 0
    since = now - timedelta(days=settings.MAILING_DOJO_NEWS_ACTIVE_DAYS)
    for dojo, events in by_dojo.items():
        ninjas = Ninja.objects.filter(
            Q(home_dojo=dojo)
            | Q(pk__in=Registration.objects.filter(event__dojo=dojo, attended=True, event__start_time__gte=since)
                .values("ninja_id"))
        )
        users = User.objects.filter(
            Q(pk__in=Guardianship.objects.filter(ninja__in=ninjas).values("guardian_id"))
            | Q(pk__in=ninjas.exclude(account=None).values("account_id")),
            is_active=True,
        ).exclude(email="").order_by("id")
        context = {
            "dojo_name": dojo.name,
            "dojo_url": settings.SITE_URL + reverse("dojo_detail", kwargs={"dojo_id": dojo.pk}),
            "events": [
                {"name": e.name, "start_time": timezone.localtime(e.start_time),
                 "url": settings.SITE_URL + reverse("event_detail", kwargs={"event_id": e.pk})}
                for e in events
            ],
        }
        key = "dojo_news:" + "-".join(str(e.pk) for e in events)
        for user in users:
            try:
                sent += _queue(user, MailCategory.DOJO_NEWS, "new_sessions_at_dojo", context, f"{key}:{user.pk}")
            except TemplateMissing:
                logger.exception("mail template new_sessions_at_dojo is missing: nothing sent")
                return sent
        Event.objects.filter(pk__in=[e.pk for e in events]).update(announced_at=now)
    return sent
