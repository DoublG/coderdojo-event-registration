from django.urls import path

from . import views

urlpatterns = [
    path(
        "manage/notifications/<int:notification_id>/open/",
        views.open_organisation_notification,
        name="open_organisation_notification",
    ),
    path(
        "manage/notifications/mark-all-read/",
        views.mark_all_organisation_notifications_read,
        name="mark_all_organisation_notifications_read",
    ),
]
