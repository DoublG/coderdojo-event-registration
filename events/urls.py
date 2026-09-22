from django.urls import path

from . import views

urlpatterns = [
    path("events/", views.event_list, name="event_list"),
    path("events/upcoming-sessions-widget/", views.upcoming_sessions_widget, name="upcoming_sessions_widget"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    path("events/<int:event_id>/signup/", views.event_signup, name="event_signup"),
]
