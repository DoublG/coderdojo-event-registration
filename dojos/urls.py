from django.urls import path

from . import views

urlpatterns = [
    path("dojos/", views.dojo_list, name="dojo_list"),
    path("dojos/finder-widget/", views.dojo_finder_widget, name="dojo_finder_widget"),
    path("dojos/<int:dojo_id>/", views.dojo_detail, name="dojo_detail"),
    path("dojos/<int:dojo_id>/team/", views.dojo_team, name="dojo_team"),
    path("dojos/<int:dojo_id>/dashboard/", views.dojo_dashboard, name="dojo_dashboard"),
    path("team/<int:mentor_id>/", views.team_member_detail, name="team_member_detail"),
]
