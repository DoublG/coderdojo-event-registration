"""Telling a session's families about a change to it (DATA_MODEL_NOTICES.md,
§31): the venue, the date or times, the places, a cancellation, or a message
of the team's own. One `SessionNotice` per notice sent, and one
`registration` mail per account (guardians and a child's own login, as the
other booking mails), sent through mailing.services.send with the dojo in
From and its address as Reply-To. Never sent without the team pressing Send.

The page that offers a notice after a save carries the values from before
the change in a signed token (`change_token`), so the mail can say what it
was without a model of pending changes."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from accounts.models import Guardianship, User
from mailing.categories import MailCategory
from mailing.models import EmailMessage
from mailing.rendering import FALLBACK_LANGUAGE, TemplateMissing, render
from mailing.services import send

from .models import Event, Registration, SessionNotice

TEMPLATES = {
    SessionNotice.VENUE_CHANGED: "session_venue_changed",
    SessionNotice.TIME_CHANGED: "session_time_changed",
    SessionNotice.PLACES_CHANGED: "session_places_changed",
    SessionNotice.CANCELLED: "session_cancelled",
    SessionNotice.MESSAGE: "session_message",
}
# The kinds the team picks on the compose page; a cancellation is sent from
# the session's Cancel page (events.services.cancel).
COMPOSE_KINDS = (
    SessionNotice.VENUE_CHANGED,
    SessionNotice.TIME_CHANGED,
    SessionNotice.PLACES_CHANGED,
    SessionNotice.MESSAGE,
)
# The values a change token carries, and which kind each one is about.
WATCHED = {
    "venue": SessionNotice.VENUE_CHANGED,
    "start_time": SessionNotice.TIME_CHANGED,
    "end_time": SessionNotice.TIME_CHANGED,
    "places": SessionNotice.PLACES_CHANGED,
}
TOKEN_SALT = "events.notice"
TOKEN_MAX_AGE = 60 * 60  # an hour: long enough to write the mail, short enough to stay current


class NoticeError(Exception):
    """A notice that can't be sent, with a message for the dojo's team."""


@dataclass(frozen=True)
class Family:
    """One account a notice goes to, with its children on the session."""

    user: User
    registrations: list[Registration]


def _registrations(event: Event, audience: str) -> list[Registration]:
    registrations = Registration.objects.filter(event=event).select_related("ninja").order_by("position", "id")
    if audience == SessionNotice.CONFIRMED:
        registrations = registrations.filter(waiting_list=False)
    elif audience == SessionNotice.WAITING_LIST:
        registrations = registrations.filter(waiting_list=True)
    return list(registrations)


def recipients(event: Event, audience: str) -> list[Family]:
    """The accounts a notice to `audience` reaches: every child's guardians
    and the child's own login with an email (mailing.automated.family_of),
    one entry per account with all its children on the session."""
    registrations = _registrations(event, audience)
    ninja_ids = [r.ninja_id for r in registrations]
    accounts_of: dict[int, set[int]] = {ninja_id: set() for ninja_id in ninja_ids}
    for ninja_id, guardian_id in Guardianship.objects.filter(ninja_id__in=ninja_ids).values_list(
        "ninja_id", "guardian_id"
    ):
        accounts_of[ninja_id].add(guardian_id)
    for registration in registrations:
        if registration.ninja.account_id:
            accounts_of[registration.ninja_id].add(registration.ninja.account_id)
    all_ids = set().union(*accounts_of.values()) if accounts_of else set()
    users = {u.pk: u for u in User.objects.filter(pk__in=all_ids, is_active=True).exclude(email="")}
    families: dict[int, Family] = {}
    for registration in registrations:
        for user_id in sorted(accounts_of[registration.ninja_id]):
            if user_id in users:
                families.setdefault(user_id, Family(users[user_id], [])).registrations.append(registration)
    return [families[user_id] for user_id in sorted(families)]


def reach(event: Event) -> dict[str, int]:
    """How many accounts each audience reaches: {audience: count}."""
    return {audience: len(recipients(event, audience)) for audience, _label in SessionNotice.AUDIENCE_CHOICES}


def sent_recently(event: Event, now: datetime | None = None) -> int:
    since = (now or timezone.now()) - timedelta(hours=24)
    return SessionNotice.objects.filter(event=event, sent_at__gte=since).count()


def can_notify(event: Event, now: datetime | None = None) -> bool:
    """Whether the session's page offers a notice at all: it has
    registrations and didn't end too long ago (the other rules are the
    compose page's, `notice_problems`)."""
    now = now or timezone.now()
    ended_long_ago = event.end_time < now - timedelta(hours=settings.SESSION_NOTICE_HOURS_AFTER_END)
    return not ended_long_ago and Registration.objects.filter(event=event).exists()


def notice_problems(notice: SessionNotice, now: datetime | None = None) -> list[str]:
    """What stops `notice` (not saved yet) from being sent, as sentences for the team."""
    now = now or timezone.now()
    event = notice.event
    problems = []
    if event.end_time < now - timedelta(hours=settings.SESSION_NOTICE_HOURS_AFTER_END):
        problems.append(_("This session ended too long ago to mail its families about it."))
    if notice.kind == SessionNotice.CANCELLED and event.status != Event.CANCELLED:
        problems.append(_("Only a cancelled session can be announced as cancelled."))
    limit = settings.SESSION_NOTICES_PER_DAY
    # The cancellation itself always goes out, whatever was sent before.
    if notice.kind != SessionNotice.CANCELLED and sent_recently(event, now) >= limit:
        problems.append(
            _("You already mailed this session's families %(limit)s times in the last 24 hours, the most you can.")
            % {"limit": limit}
        )
    if not recipients(event, notice.audience):
        problems.append(_("Nobody to mail: no family of this session has an email address in that group."))
    return problems


def _names(names: list[str], language: str) -> str:
    """ "Emma", "Emma and Lucas", "Emma, Lucas and Noor", in `language`."""
    if len(names) < 2:
        return "".join(names)
    with translation.override(language):
        return _("%(names)s and %(last)s") % {"names": ", ".join(names[:-1]), "last": names[-1]}


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    return timezone.localtime(datetime.fromisoformat(value))


def notice_context(notice: SessionNotice, family: Family) -> dict[str, Any]:
    """The template variables for one account, in its mail language."""
    event = notice.event
    dojo = event.dojo
    language = family.user.preferred_language or FALLBACK_LANGUAGE
    changes = notice.changes or {}
    context: dict[str, Any] = {
        "ninja_names": _names([r.ninja.name for r in family.registrations], language),
        "children": [{"name": r.ninja.name, "waiting_list": r.waiting_list} for r in family.registrations],
        "event_name": str(event.localized("name", language)),
        "dojo_name": dojo.name,
        # An organisation dojo, or one that isn't public, has no page of its own.
        "dojo_url": settings.SITE_URL
        + (reverse("dojo_detail", kwargs={"dojo_id": dojo.pk}) if dojo.is_public else "/"),
        "start_time": timezone.localtime(event.start_time),
        "end_time": timezone.localtime(event.end_time),
        "venue": event.venue_name or dojo.address or dojo.name,
        "places": event.places,
        "event_url": settings.SITE_URL + reverse("event_detail", kwargs={"event_id": event.pk}),
        "account_url": settings.SITE_URL + reverse("account_home"),
        "subject": str(notice.localized("subject", language)),
        "message": str(notice.localized("message", language)),
        "can_reply": bool(dojo.email),
    }
    if "venue" in changes:
        context["old_venue"] = changes["venue"][0]
    if "start_time" in changes:
        context["old_start_time"] = _parse(changes["start_time"][0])
        context["old_end_time"] = _parse(changes["end_time"][0])
    if "places" in changes:
        context["old_places"] = changes["places"][0]
    return context


def preview(notice: SessionNotice, user: User) -> tuple[str, str] | None:
    """(subject, body) of `notice` as the first family gets it, with
    `user`'s name and language: for the compose page. None when nobody
    would get it."""
    families = recipients(notice.event, notice.audience)
    if not families:
        return None
    family = Family(user, families[0].registrations)
    context = {"recipient_name": user.first_name or user.get_username(), "site_url": settings.SITE_URL}
    context.update(notice_context(notice, family))
    return render(TEMPLATES[notice.kind], user.preferred_language or FALLBACK_LANGUAGE, context)


def send_notice(notice: SessionNotice) -> SessionNotice:
    """Check `notice` (not saved yet: event, kind, audience, texts, changes,
    sent_by), save it and queue one mail per account. The session's row is
    locked, so two sends at once can't pass the daily limit together. Raises
    NoticeError with the first problem; then nothing is saved or queued."""
    with transaction.atomic():
        Event.objects.select_for_update().filter(pk=notice.event_id).first()
        problems = notice_problems(notice)
        if problems:
            raise NoticeError(problems[0])
        notice.sent_at = timezone.now()
        notice.save()
        queued = 0
        dojo = notice.event.dojo
        try:
            for family in recipients(notice.event, notice.audience):
                row = send(
                    family.user,
                    MailCategory.REGISTRATION,
                    TEMPLATES[notice.kind],
                    notice_context(notice, family),
                    idempotency_key=f"session_notice:{notice.pk}:{family.user.pk}",
                    dojo=dojo,
                    reply_to=dojo.email or "",
                )
                queued += row.status == EmailMessage.Status.PENDING
        except TemplateMissing as error:
            raise NoticeError(_("This mail is missing on the site. Please tell the organisation.")) from error
        notice.recipients = queued
        notice.save(update_fields=["recipients"])
        return notice


def changed_kinds(event: Event, before: dict[str, Any]) -> list[str]:
    """The kinds of notice a change from `before` (from `snapshot`) to the
    event as it is now calls for, in COMPOSE_KINDS' order."""
    now = snapshot(event)
    kinds = {kind for field, kind in WATCHED.items() if field in before and before[field] != now[field]}
    return [kind for kind in COMPOSE_KINDS if kind in kinds]


def snapshot(event: Event) -> dict[str, Any]:
    """The watched values of `event`, as a change token carries them."""
    return {
        "venue": event.venue_name,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "places": event.places,
    }


def change_token(event: Event, before: dict[str, Any]) -> str:
    return signing.dumps({"event": event.pk, **before}, salt=TOKEN_SALT)


def read_change_token(token: str, event: Event) -> dict[str, Any] | None:
    """The values from before the change, or None for a token that's
    missing, tampered with, too old or about another session."""
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict) or data.pop("event", None) != event.pk:
        return None
    return {field: data[field] for field in WATCHED if field in data}


def changes_for(kind: str, event: Event, before: dict[str, Any]) -> dict[str, list[Any]]:
    """What a notice of `kind` shows as changed: {field: [before, now]}."""
    now = snapshot(event)
    fields = [field for field, field_kind in WATCHED.items() if field_kind == kind]
    return {field: [before.get(field), now[field]] for field in fields if field in before}
