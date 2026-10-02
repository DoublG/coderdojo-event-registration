"""The dojo admin area's notification bell: opening a notification and marking
them all read (the live updates are notifications.consumers)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from notifications.models import Notification

from ..access import require_dojo_access
from .common import _notification_context


@login_required
def open_notification(request, dojo_id, notification_id):
    """What a notification item's link actually points at (see
    _notification_bell.html) — marks it read then sends the owner on to
    wherever it's actually about, matching the design system's own "clicking
    one should... typically navigate" guidance. A plain GET/redirect, not
    htmx: this is a real navigation, not an in-place update.

    recipient=request.user (on top of the usual dojo-ownership check) matters
    here specifically — read state is per-recipient, so one owner must not
    be able to mark a co-owner's copy of a dojo-level notification read."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user, dojo=dojo)
    if not notification.read:
        notification.read = True
        notification.save(update_fields=["read"])
    return redirect(notification.url or reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))


@login_required
def mark_all_notifications_read(request, dojo_id):
    """The bell panel's "Mark all as read" — htmx (hx-swap="none" on the
    form, see _notification_bell.html): the response's own hx-swap-oob="true"
    root is what actually places it, so no target/swap mode needs setting
    here beyond suppressing htmx's normal (non-oob) placement."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    if request.method == "POST":
        Notification.objects.filter(recipient=request.user, dojo=dojo, read=False).update(read=True)
    return render(
        request,
        "dojos/partials/_notification_bell.html",
        {
            "dojo": dojo,
            **_notification_context(request.user, dojo),
        },
    )
