"""What the dojos app's pages share: page sizes and the dojo admin area's context
(sidebar, switcher, notification bell)."""

from notifications.models import Notification

RESULTS_PER_PAGE = 20


WIDGET_RESULTS_LIMIT = 5


NOTIFICATION_LIMIT = 10


# How many of a dojo's newest updates its public page shows ("From this dojo").
PUBLIC_UPDATES_LIMIT = 5


def _admin_context(request, access):
    """What every page extending dojos/_admin_base.html needs besides its
    own content: the dojo, the viewer's role/capabilities (`dojo_access`,
    see dojos.access) and the notification bell. What they can switch
    between comes from accounts.manage_nav (the manage_switcher tag)."""
    return {
        "dojo": access.dojo,
        "dojo_access": access,
        **_notification_context(request.user, access.dojo),
    }


def _notification_context(user, dojo):
    """Shared by every admin view that renders dojos/templates/dojos/
    partials/_notification_bell.html on initial page load — the exact
    same query shape notifications.consumers.NotificationConsumer and
    mark_all_notifications_read below use for their own re-renders, kept
    in one place so "what counts as this dojo's notifications for this
    user" can't drift between the three."""
    notifications = Notification.objects.filter(recipient=user, dojo=dojo)[:NOTIFICATION_LIMIT]
    unread_count = Notification.objects.filter(recipient=user, dojo=dojo, read=False).count()
    return {"notifications": notifications, "unread_count": unread_count}
