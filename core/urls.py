from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),

    # events
    path("event/search", views.events, name="event_list"),
    path("event/<int:event_id>/signup", views.signup_event, name="signup_event"),
    path("event/<int:event_id>", views.event, name="event_detail"),

    # dojos
    path("dojo/search", views.dojo_list, name="dojo_list"),
    path("dojo/<int:dojo_id>/team", views.team, name="dojo_team"),
    path("dojo/<int:dojo_id>", views.dojo, name="dojo_detail"),
    path("dojo/<int:dojo_id>/event/<int:event_id>", views.events, name="event_list_by_dojo"), #needed for back button on event detail page

    path("guardian/<int:guardian_id>", views.guardian, name="guardian_detail"),
    path("guardian/<int:guardian_id>/child/<int:child_id>", views.child, name="child_detail"),

    path("profile/<int:profile_id>", views.profile, name="profile_detail"),

    path("pathway/<int:pathway_id>", views.pathway, name="pathway_detail"),

    # registration
    path("register/helper", views.register_helper, name="register_helper"),
    path("register/dojo", views.register_dojo, name="register_dojo"),
    path("register/guardian", views.register_guardian, name="register_guardian"),
    path("register", views.register, name="register"),
    
    path("manage", views.admin, name="manage"),
    path("login", views.login, name="login"),
]