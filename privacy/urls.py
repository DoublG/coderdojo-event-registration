from django.urls import path

from . import views

urlpatterns = [
    path("account/data/", views.download_my_data, name="download_my_data"),
    path("manage/privacy/", views.manage_privacy, name="manage_privacy"),
    path("manage/privacy/<int:user_id>/export/", views.manage_privacy_export, name="manage_privacy_export"),
]
