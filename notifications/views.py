"""The organisation dashboard's notification bell (DATA_MODEL.md §23): open
one notification, and mark them all read. A dojo's bell has its own views
in dojos.views; both render dojos/partials/_notification_bell.html."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.manage_nav import require_organisation_context

from .consumers import organisation_notification_context
from .models import Notification


@login_required
def open_organisation_notification(request, notification_id):
    """Marks it read and goes where it's about; only the recipient's own."""
    require_organisation_context(request)
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user, organisation=True)
    if not notification.read:
        notification.read = True
        notification.save(update_fields=["read"])
    return redirect(notification.url or reverse("manage_home"))


@login_required
def mark_all_organisation_notifications_read(request):
    """The bell's "Mark all as read" (htmx; the partial places itself)."""
    require_organisation_context(request)
    if request.method == "POST":
        Notification.objects.filter(recipient=request.user, organisation=True, read=False).update(read=True)
    return render(request, "dojos/partials/_notification_bell.html", organisation_notification_context(request.user))
