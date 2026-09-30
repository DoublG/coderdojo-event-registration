from django.urls import path

from . import audit_views, health, manage, views

urlpatterns = [
    path("", views.home, name="home"),
    path("contact/", views.contact, name="contact"),
    path("code-of-conduct/", views.code_of_conduct, name="code_of_conduct"),
    path("health/", health.health, name="health"),
    path("manage/", manage.manage_home, name="manage_home"),
    path("manage/audit-log/", audit_views.manage_audit_log, name="manage_audit_log"),
]
