from django.urls import path

from . import manage, views

urlpatterns = [
    # The organisation dashboard's Awards page (organisation admin role only).
    path("manage/awards/", manage.badge_list, name="manage_badge_list"),
    path("manage/awards/new/", manage.badge_create, name="manage_badge_create"),
    path("manage/awards/<int:badge_id>/", manage.badge_detail, name="manage_badge_detail"),
    path("manage/awards/<int:badge_id>/delete/", manage.badge_delete, name="manage_badge_delete"),
    path("events/", views.event_list, name="event_list"),
    path("events/upcoming-sessions-widget/", views.upcoming_sessions_widget, name="upcoming_sessions_widget"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("events/<int:event_id>/signup/", views.event_signup, name="event_signup"),
]
