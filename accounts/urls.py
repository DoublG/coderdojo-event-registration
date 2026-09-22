from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login, name="login"),
    path("register/", views.register, name="register"),
    path("register/guardian/", views.register_guardian, name="register_guardian"),
    path("guardian/<int:guardian_id>/", views.guardian_detail, name="guardian_detail"),
    path("guardian/<int:guardian_id>/child/<int:child_id>/", views.child_detail, name="child_detail"),
]
