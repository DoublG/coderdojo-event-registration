from django.urls import path

from . import manage, views

urlpatterns = [
    path("account/mail/", views.mail_preferences, name="mail_preferences"),
    path("mail/unsubscribe/<str:token>/", views.mail_unsubscribe, name="mail_unsubscribe"),
    path("manage/templates/", manage.template_list, name="manage_template_list"),
    path("manage/templates/new/", manage.template_create, name="manage_template_create"),
    path("manage/templates/<slug:key>/delete/", manage.template_delete, name="manage_template_delete"),
    path("manage/templates/<slug:key>/<str:language>/", manage.template_edit, name="manage_template_edit"),
    path(
        "manage/templates/<slug:key>/<str:language>/delete/",
        manage.template_delete,
        name="manage_template_delete_language",
    ),
    path("manage/mail/", manage.mail_queue, name="manage_mail_queue"),
    path("manage/mail/log/", manage.mail_log, name="manage_mail_log"),
    path("manage/mail/retry-failed/", manage.mail_retry_failed, name="manage_mail_retry_failed"),
    path("manage/mail/<int:message_id>/retry/", manage.mail_retry, name="manage_mail_retry"),
    path("manage/mail/blocked/<int:suppression_id>/unblock/", manage.mail_unblock, name="manage_mail_unblock"),
    path("manage/mail/blocked/new/", manage.mail_block, name="manage_mail_block"),
]
