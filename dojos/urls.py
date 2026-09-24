from django.urls import path

from . import views

urlpatterns = [
    path("dojos/", views.dojo_list, name="dojo_list"),
    path("dojos/finder-widget/", views.dojo_finder_widget, name="dojo_finder_widget"),
    path("dojos/new/", views.dojo_create, name="dojo_create"),
    path("dojos/<int:dojo_id>/", views.dojo_detail, name="dojo_detail"),
    path("dojos/<int:dojo_id>/team/", views.dojo_team, name="dojo_team"),
    path("dojos/<int:dojo_id>/join/", views.dojo_join_request, name="dojo_join_request"),
    path("dojos/<int:dojo_id>/dashboard/", views.dojo_dashboard, name="dojo_dashboard"),
    path("dojos/<int:dojo_id>/manage/", views.dojo_manage, name="dojo_manage"),
    path("dojos/<int:dojo_id>/manage/lifecycle/", views.dojo_set_lifecycle, name="dojo_set_lifecycle"),
    path("dojos/<int:dojo_id>/manage/team/", views.dojo_team_manage, name="dojo_team_manage"),
    path("dojos/<int:dojo_id>/manage/team/action/", views.dojo_team_action, name="dojo_team_action"),
    path("dojos/<int:dojo_id>/events/", views.dojo_event_list, name="dojo_event_list"),
    path("dojos/<int:dojo_id>/events/new/", views.dojo_event_create, name="dojo_event_create"),
    path("dojos/<int:dojo_id>/events/<int:event_id>/", views.dojo_event_detail, name="dojo_event_detail"),
    path(
        "dojos/<int:dojo_id>/events/<int:event_id>/attendance/",
        views.dojo_event_attendance,
        name="dojo_event_attendance",
    ),
    path(
        "dojos/<int:dojo_id>/events/<int:event_id>/attendance/mark-all/",
        views.dojo_event_attendance_mark_all,
        name="dojo_event_attendance_mark_all",
    ),
    path(
        "dojos/<int:dojo_id>/events/<int:event_id>/attendance/<int:registration_id>/belt/",
        views.dojo_event_award_belt,
        name="dojo_event_award_belt",
    ),
    path(
        "dojos/<int:dojo_id>/events/<int:event_id>/attendance/<int:registration_id>/pathways/",
        views.dojo_event_registration_pathways,
        name="dojo_event_registration_pathways",
    ),
    path(
        "dojos/<int:dojo_id>/events/<int:event_id>/attendance/<int:registration_id>/",
        views.dojo_event_attendance_mark,
        name="dojo_event_attendance_mark",
    ),
    path(
        "dojos/<int:dojo_id>/events/<int:event_id>/status/",
        views.dojo_event_set_status,
        name="dojo_event_set_status",
    ),
    path(
        "dojos/<int:dojo_id>/notifications/<int:notification_id>/open/",
        views.open_notification,
        name="open_notification",
    ),
    path(
        "dojos/<int:dojo_id>/notifications/mark-all-read/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),
    path("team/<int:member_id>/", views.team_member_detail, name="team_member_detail"),
]
