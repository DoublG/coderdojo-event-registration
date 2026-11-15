"""A visitor's message to a dojo's team (the Send a message form on a dojo's
page): a mail to the dojo's champion and mentors, Reply-To the visitor,
through the mail engine. No account needed, so it's limited without any
third party: per client address, per email address and per dojo, each over
an hour, plus a honeypot field in the form (dojos.forms.DojoContactForm)."""

import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext as _

from mailing.categories import MailCategory
from mailing.services import send

from .models import Dojo

WINDOW_SECONDS = 3600
# Messages per hour: one visitor can write a few times, a dojo never gets a flood.
LIMIT_PER_IP = 3
LIMIT_PER_EMAIL = 3
LIMIT_PER_DOJO = 20


class ContactError(Exception):
    """A message that can't be sent now, with a message for the visitor."""


def client_ip(request: HttpRequest) -> str:
    """The visitor's address as our own proxy saw it: the last entry of
    X-Forwarded-For (the ones before it are whatever the client sent)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    last = forwarded.split(",")[-1].strip()
    return last or request.META.get("REMOTE_ADDR", "")


def _over_limit(kind: str, value: str, limit: int) -> bool:
    """Count one more message for `value` in the last hour and say whether
    that's past `limit`. Only a hash is kept, never the address itself."""
    key = f"dojo-contact:{kind}:{hashlib.sha256(value.lower().encode()).hexdigest()[:32]}"
    cache.add(key, 0, WINDOW_SECONDS)
    try:
        return int(cache.incr(key)) > limit
    except ValueError:  # the key expired between the two calls
        cache.set(key, 1, WINDOW_SECONDS)
        return 1 > limit


def send_message(dojo: Dojo, *, name: str, email: str, message: str, ip: str) -> int:
    """Mail `message` to the dojo's champion and mentors, Reply-To `email`.
    Returns how many were queued. Raises ContactError when a limit is
    reached or the dojo has nobody to send to."""
    recipients = [m.user for m in dojo.memberships.managers().select_related("user")]
    if not recipients:
        raise ContactError(_("This dojo can't receive messages right now."))
    over = [
        _over_limit("ip", ip or "unknown", LIMIT_PER_IP),
        _over_limit("email", email, LIMIT_PER_EMAIL),
        _over_limit("dojo", str(dojo.pk), LIMIT_PER_DOJO),
    ]
    if any(over):
        raise ContactError(_("Too many messages for now: please try again in an hour."))
    # One line: the name goes in the subject.
    sender = " ".join(name.split())
    context = {
        "dojo_name": dojo.name,
        "dojo_url": f"{settings.SITE_URL}{reverse('dojo_detail', args=[dojo.pk])}",
        "sender_name": sender,
        "sender_email": email,
        "message": message.strip(),
    }
    for user in recipients:
        send(user, MailCategory.SERVICE, "dojo_contact_message", context, reply_to=email)
    return len(recipients)
