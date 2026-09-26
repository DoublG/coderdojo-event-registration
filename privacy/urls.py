from django.urls import path

from . import views

urlpatterns = [
    path("account/data/", views.download_my_data, name="download_my_data"),
    path("account/delete/", views.delete_my_account, name="delete_my_account"),
    path("manage/privacy/", views.manage_privacy, name="manage_privacy"),
    path("manage/privacy/<int:user_id>/export/", views.manage_privacy_export, name="manage_privacy_export"),
    path("manage/privacy/<int:user_id>/delete/", views.manage_privacy_delete, name="manage_privacy_delete"),
]
