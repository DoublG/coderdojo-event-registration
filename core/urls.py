from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),

    # events
    path("events", views.events, name="event_list"),
    path("event/<int:event_id>/signup", views.signup_event, name="signup_event"),
    path("event/<int:event_id>", views.event, name="event_detail"),

    # dojos
    path("dojo/<int:dojo_id>/team", views.team, name="dojo_team"),
    path("dojo/<int:dojo_id>", views.dojo, name="dojo_detail"),

    path("guardian/<int:guardian_id>", views.guardian, name="guardian_detail"),
    path("guardian/<int:guardian_id>/child/<int:child_id>", views.child, name="child_detail"),

    path("profile/<int:profile_id>", views.profile, name="profile_detail"),

    path("register", views.register, name="register"),
    
    path("manage", views.admin, name="manage"),
    path("login", views.login, name="login"),
]