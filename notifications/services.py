from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.utils import translation

from .models import Notification


def _group_name(recipient_id):
    return f"notifications_user_{recipient_id}"


def notify(recipient, text, url="", dojo=None, params=None):
    """Creates a Notification and nudges that recipient's open WebSocket
    connection(s) (notifications.consumers.NotificationConsumer) to
    re-render and push themselves — see dojos.templates.dojos.partials.
    _notification_bell.html, the single source of truth both the initial
    page render and every push re-render from.

    The DB row is the source of truth; the push is best-effort. A channel
    layer hiccup (Redis unreachable, no consumer currently connected —
    group_send to an empty group is a normal no-op, not an error) must
    never break whatever action triggered this notification, so it's
    caught here rather than left to the caller.

    The text is stored as it's shown, so it's written in the recipient's
    language: pass a gettext_lazy() message and its `params` (the
    %(name)s values), and it's rendered here under the recipient's
    preferred_language."""
    with translation.override(recipient.preferred_language or settings.LANGUAGE_CODE):
        text = str(text) % params if params else str(text)
    notification = Notification.objects.create(recipient=recipient, text=text, url=url, dojo=dojo)

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        try:
            async_to_sync(channel_layer.group_send)(
                _group_name(recipient.id), {"type": "notification.push"},
            )
        except Exception:
            pass

    return notification
