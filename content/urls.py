from django.urls import path

from . import manage

urlpatterns = [
    # The organisation dashboard's Promotions page (organisation admin role only).
    path("manage/promotions/", manage.promotion_list, name="manage_promotion_list"),
    path("manage/promotions/new/", manage.promotion_create, name="manage_promotion_create"),
    path("manage/promotions/<int:promotion_id>/", manage.promotion_detail, name="manage_promotion_detail"),
    path("manage/promotions/<int:promotion_id>/delete/", manage.promotion_delete, name="manage_promotion_delete"),
    # ... and its Sponsors page (the homepage's "Made possible by").
    path("manage/sponsors/", manage.sponsor_list, name="manage_sponsor_list"),
    path("manage/sponsors/new/", manage.sponsor_create, name="manage_sponsor_create"),
    path("manage/sponsors/<int:sponsor_id>/", manage.sponsor_detail, name="manage_sponsor_detail"),
    path("manage/sponsors/<int:sponsor_id>/delete/", manage.sponsor_delete, name="manage_sponsor_delete"),
]
