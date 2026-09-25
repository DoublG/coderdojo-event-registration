from django.urls import path

from . import manage, views

urlpatterns = [
    path("account/mail/", views.mail_preferences, name="mail_preferences"),
    path("mail/unsubscribe/<str:token>/", views.mail_unsubscribe, name="mail_unsubscribe"),
    # The organisation's management dashboard (organisation admin role only).
    path("manage/", manage.manage_home, name="manage_home"),
    path("manage/campaigns/", manage.campaign_list, name="manage_campaign_list"),
    path("manage/campaigns/new/", manage.campaign_create, name="manage_campaign_create"),
    path("manage/campaigns/<int:campaign_id>/", manage.campaign_detail, name="manage_campaign_detail"),
    path("manage/campaigns/<int:campaign_id>/test/", manage.campaign_test, name="manage_campaign_test"),
    path("manage/campaigns/<int:campaign_id>/launch/", manage.campaign_launch, name="manage_campaign_launch"),
    path("manage/campaigns/<int:campaign_id>/cancel/", manage.campaign_cancel, name="manage_campaign_cancel"),
    path("manage/segments/", manage.segment_list, name="manage_segment_list"),
]
