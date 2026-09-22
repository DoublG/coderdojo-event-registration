from django.contrib import admin
from django.urls import reverse

from accounts.models import DojoOwner, HelperAccount
from accounts.provisioning import provision_account

from .models import DojoApplication, MentorApplication


@admin.action(description="Approve & email a DojoOwner login to the applicant")
def approve_and_provision_owner(modeladmin, request, queryset):
    login_url = request.build_absolute_uri(reverse("login"))
    approved = 0
    for application in queryset.exclude(status=DojoApplication.APPROVED):
        provision_account(DojoOwner, application.applicant_name, application.applicant_email, login_url)
        application.status = DojoApplication.APPROVED
        application.save(update_fields=["status"])
        approved += 1
    modeladmin.message_user(request, f"Provisioned {approved} DojoOwner account(s) and emailed their temp password.")


@admin.action(description="Approve & email a helper login to the applicant")
def approve_and_provision_helper(modeladmin, request, queryset):
    login_url = request.build_absolute_uri(reverse("login"))
    approved = 0
    for application in queryset.exclude(status=MentorApplication.APPROVED):
        provision_account(HelperAccount, application.applicant_name, application.applicant_email, login_url)
        application.status = MentorApplication.APPROVED
        application.save(update_fields=["status"])
        approved += 1
    modeladmin.message_user(request, f"Provisioned {approved} helper account(s) and emailed their temp password.")


@admin.register(DojoApplication)
class DojoApplicationAdmin(admin.ModelAdmin):
    list_display = ["applicant_name", "applicant_email", "area", "status", "submitted_at"]
    list_filter = ["status"]
    actions = [approve_and_provision_owner]


@admin.register(MentorApplication)
class MentorApplicationAdmin(admin.ModelAdmin):
    list_display = ["applicant_name", "applicant_email", "role", "dojo", "status", "submitted_at"]
    list_filter = ["status", "role"]
    actions = [approve_and_provision_helper]
