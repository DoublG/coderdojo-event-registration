from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string


def _notification_context(user, dojo_id):
    from dojos.models import Dojo

    from .models import Notification

    dojo = Dojo.objects.filter(id=dojo_id).first()
    notifications = list(Notification.objects.filter(recipient=user, dojo_id=dojo_id)[:10])
    unread_count = Notification.objects.filter(recipient=user, dojo_id=dojo_id, read=False).count()
    return {"dojo": dojo, "notifications": notifications, "unread_count": unread_count}


@database_sync_to_async
def _has_dojo_access(user, dojo_id):
    from dojos.access import dojo_role
    from dojos.models import Dojo

    dojo = Dojo.objects.filter(id=dojo_id).first()
    return dojo is not None and dojo_role(user, dojo) is not None


class NotificationConsumer(AsyncWebsocketConsumer):
    """Backs ws://.../ws/dojos/<dojo_id>/notifications/ (see routing.py) —
    one connection per open admin page. Joins a per-*user* group (not
    per-dojo: a user only ever has one of these open at a time in
    practice, and keeping the group per-user is simpler than the admin
    pages needing to know which dojo tabs are open elsewhere) and, on
    every group event, re-renders this connection's own dojo-scoped view
    of the notification bell fresh from the DB and pushes it as one
    hx-swap-oob fragment — see dojos/templates/dojos/partials/
    _notification_bell.html, the same partial the initial page load and
    the mark-all-read htmx endpoint both render from.

    Admin access (owner or helper — see dojos.access) is checked once, at
    connect time, the same 404-not-403 reasoning as
    dojos.access.require_dojo_access: a mismatch just refuses the
    connection rather than accepting it, so a guessed dojo_id doesn't even
    confirm that dojo exists to someone without access to it."""

    async def connect(self):
        user = self.scope["user"]
        self.dojo_id = self.scope["url_route"]["kwargs"]["dojo_id"]

        if not user.is_authenticated or not await _has_dojo_access(user, self.dojo_id):
            await self.close()
            return

        self.group_name = f"notifications_user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_push(self, event):
        """Handles a `{"type": "notification.push"}` group-send from
        notifications.services.notify() — Channels dispatches a group
        event's `type` (dots converted to underscores) to the
        same-named consumer method."""
        context = await database_sync_to_async(_notification_context)(self.scope["user"], self.dojo_id)
        html = await database_sync_to_async(render_to_string)(
            "dojos/partials/_notification_bell.html", context,
        )
        await self.send(text_data=html)
