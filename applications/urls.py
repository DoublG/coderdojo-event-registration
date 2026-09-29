from django.urls import path

from . import manage, views

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
    # The organisation dashboard's Volunteers pages (reviewer role only, DATA_MODEL.md §21).
    path("manage/checks/", manage.check_list, name="manage_check_list"),
    path("manage/checks/<int:user_id>/", manage.check_detail, name="manage_check_detail"),
    path("manage/checks/<int:user_id>/decide/", manage.check_decide, name="manage_check_decide"),
    path("manage/checks/<int:user_id>/request/", manage.check_request, name="manage_check_request"),
    path("manage/applications/", manage.application_list, name="manage_application_list"),
    path(
        "manage/applications/<int:application_id>/",
        manage.application_detail,
        name="manage_application_detail",
    ),
    path(
        "manage/applications/<int:application_id>/decide/",
        manage.application_decide,
        name="manage_application_decide",
    ),
]
