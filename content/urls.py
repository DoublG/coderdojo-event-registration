from django.urls import path

from . import manage

urlpatterns = [
    # The organisation dashboard's Promotions page (organisation admin role only).
    path("manage/promotions/", manage.promotion_list, name="manage_promotion_list"),
    path("manage/promotions/new/", manage.promotion_create, name="manage_promotion_create"),
    path("manage/promotions/<int:promotion_id>/", manage.promotion_detail, name="manage_promotion_detail"),
    path("manage/promotions/<int:promotion_id>/delete/", manage.promotion_delete, name="manage_promotion_delete"),
]
