from django.urls import path

from . import views

urlpatterns = [
    path("register/dojo/", views.register_dojo, name="register_dojo"),
    path("register/helper/", views.register_helper, name="register_helper"),
    path(
        "applications/background-check/<uuid:token>/",
        views.upload_background_check,
        name="upload_background_check",
    ),
    path(
        "account/background-check/renew/",
        views.renew_background_check,
        name="renew_background_check",
    ),
    path(
        "applications/background-check/<int:user_id>/document/",
        views.download_background_check,
        name="download_background_check",
    ),
]
