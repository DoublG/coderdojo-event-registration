from django.urls import path

from . import views

urlpatterns = [
    path("dojos/", views.dojo_list, name="dojo_list"),
    path("dojos/<int:dojo_id>/", views.dojo_detail, name="dojo_detail"),
    path("dojos/<int:dojo_id>/team/", views.dojo_team, name="dojo_team"),
    path("dojos/<int:dojo_id>/dashboard/", views.dojo_dashboard, name="dojo_dashboard"),
    path("mentors/<int:mentor_id>/", views.mentor_profile, name="mentor_profile"),
]
