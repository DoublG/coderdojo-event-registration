from django.urls import path

from . import dojo_views, manage, views

urlpatterns = [
    path("account/mail/", views.mail_preferences, name="mail_preferences"),
    path("mail/unsubscribe/<str:token>/", views.mail_unsubscribe, name="mail_unsubscribe"),
    # A dojo's own mail to its families (the dojo's admin area, DATA_MODEL.md §25).
    path("dojos/<int:dojo_id>/manage/mail/", dojo_views.dojo_mail_list, name="dojo_mail_list"),
    path("dojos/<int:dojo_id>/manage/mail/new/", dojo_views.dojo_mail_create, name="dojo_mail_create"),
    path("dojos/<int:dojo_id>/manage/mail/reach/", dojo_views.dojo_mail_reach, name="dojo_mail_reach"),
    path("dojos/<int:dojo_id>/manage/mail/<int:campaign_id>/", dojo_views.dojo_mail_detail, name="dojo_mail_detail"),
    path("dojos/<int:dojo_id>/manage/mail/<int:campaign_id>/test/", dojo_views.dojo_mail_test, name="dojo_mail_test"),
    path(
        "dojos/<int:dojo_id>/manage/mail/<int:campaign_id>/send/",
        dojo_views.dojo_mail_launch,
        name="dojo_mail_launch",
    ),
    path(
        "dojos/<int:dojo_id>/manage/mail/<int:campaign_id>/cancel/",
        dojo_views.dojo_mail_cancel,
        name="dojo_mail_cancel",
    ),
    # The organisation's management dashboard (organisation admin role only).
    path("manage/campaigns/", manage.campaign_list, name="manage_campaign_list"),
    path("manage/campaigns/new/", manage.campaign_create, name="manage_campaign_create"),
    path("manage/campaigns/<int:campaign_id>/", manage.campaign_detail, name="manage_campaign_detail"),
    path("manage/campaigns/<int:campaign_id>/test/", manage.campaign_test, name="manage_campaign_test"),
    path("manage/campaigns/<int:campaign_id>/launch/", manage.campaign_launch, name="manage_campaign_launch"),
    path("manage/campaigns/<int:campaign_id>/cancel/", manage.campaign_cancel, name="manage_campaign_cancel"),
    path("manage/templates/", manage.template_list, name="manage_template_list"),
    path("manage/templates/new/", manage.template_create, name="manage_template_create"),
    path("manage/templates/<slug:key>/delete/", manage.template_delete, name="manage_template_delete"),
    path("manage/templates/<slug:key>/<str:language>/", manage.template_edit, name="manage_template_edit"),
    path(
        "manage/templates/<slug:key>/<str:language>/delete/",
        manage.template_delete,
        name="manage_template_delete_language",
    ),
    path("manage/journeys/", manage.journey_list, name="manage_journey_list"),
    path("manage/journeys/new/", manage.journey_create, name="manage_journey_create"),
    path("manage/journeys/<int:journey_id>/", manage.journey_detail, name="manage_journey_detail"),
    path("manage/journeys/<int:journey_id>/activate/", manage.journey_activate, name="manage_journey_activate"),
    path("manage/journeys/<int:journey_id>/pause/", manage.journey_pause, name="manage_journey_pause"),
    path("manage/journeys/<int:journey_id>/test/", manage.journey_test, name="manage_journey_test"),
    path("manage/mail/", manage.mail_queue, name="manage_mail_queue"),
    path("manage/segments/", manage.segment_list, name="manage_segment_list"),
    path("manage/segments/new/", manage.segment_create, name="manage_segment_create"),
    path("manage/segments/<int:segment_id>/", manage.segment_detail, name="manage_segment_detail"),
    path("manage/segments/<int:segment_id>/delete/", manage.segment_delete, name="manage_segment_delete"),
    path("manage/segments/<int:segment_id>/groups/", manage.segment_add_group, name="manage_segment_add_group"),
    path(
        "manage/segments/<int:segment_id>/groups/<int:group_id>/",
        manage.segment_update_group,
        name="manage_segment_update_group",
    ),
    path(
        "manage/segments/<int:segment_id>/groups/<int:group_id>/delete/",
        manage.segment_delete_group,
        name="manage_segment_delete_group",
    ),
    path(
        "manage/segments/<int:segment_id>/groups/<int:group_id>/rule-fields/",
        manage.segment_rule_fields,
        name="manage_segment_rule_fields",
    ),
    path(
        "manage/segments/<int:segment_id>/groups/<int:group_id>/rules/",
        manage.segment_add_rule,
        name="manage_segment_add_rule",
    ),
    path(
        "manage/segments/<int:segment_id>/rules/<int:rule_id>/delete/",
        manage.segment_delete_rule,
        name="manage_segment_delete_rule",
    ),
]
