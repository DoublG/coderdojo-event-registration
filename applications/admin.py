from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from accounts.models import DojoOwner, HelperAccount
from accounts.provisioning import provision_account

from .models import BACKGROUND_CHECK_VALIDITY, BackgroundCheckMixin, DojoApplication, MentorApplication
from .services import send_background_check_request


@admin.action(description="Request background check document from applicant")
def request_background_check(modeladmin, request, queryset):
    sent = 0
    for application in queryset.exclude(background_check_status=BackgroundCheckMixin.VALIDATED):
        send_background_check_request(application, request)
        sent += 1
    modeladmin.message_user(request, f"Emailed {sent} applicant(s) with the document upload link.")


@admin.action(description="Mark background check as validated")
def validate_background_check(modeladmin, request, queryset):
    if not request.user.has_perm("applications.can_review_background_checks"):
        modeladmin.message_user(request, "You don't have permission to review background checks.", level="error")
        return
    now = timezone.now()
    validated = 0
    for application in queryset.exclude(background_check_document=""):
        # The document (a criminal record extract) is only needed for this
        # decision, not afterwards — keep the outcome and its expiry, drop
        # the file itself.
        application.background_check_document.delete(save=False)
        application.background_check_status = BackgroundCheckMixin.VALIDATED
        application.background_check_reviewed_at = now
        application.background_check_expires_at = now + BACKGROUND_CHECK_VALIDITY
        application.save(update_fields=[
            "background_check_document", "background_check_status",
            "background_check_reviewed_at", "background_check_expires_at",
        ])
        validated += 1
    modeladmin.message_user(request, f"Validated {validated} background check(s); documents discarded.")


@admin.action(description="Reject background check document")
def reject_background_check(modeladmin, request, queryset):
    if not request.user.has_perm("applications.can_review_background_checks"):
        modeladmin.message_user(request, "You don't have permission to review background checks.", level="error")
        return
    updated = queryset.update(
        background_check_status=BackgroundCheckMixin.REJECTED, background_check_reviewed_at=timezone.now(),
    )
    modeladmin.message_user(request, f"Rejected {updated} background check document(s).")


@admin.action(description="Approve & email a DojoOwner login to the applicant")
def approve_and_provision_owner(modeladmin, request, queryset):
    login_url = request.build_absolute_uri(reverse("login"))
    approved, blocked = 0, 0
    for application in queryset.exclude(status=DojoApplication.APPROVED):
        if not application.has_valid_background_check:
            blocked += 1
            continue
        provision_account(DojoOwner, application.applicant_name, application.applicant_email, login_url)
        application.status = DojoApplication.APPROVED
        application.save(update_fields=["status"])
        approved += 1
    message = f"Provisioned {approved} DojoOwner account(s) and emailed their temp password."
    if blocked:
        message += f" Skipped {blocked} without a valid (non-expired) background check."
    modeladmin.message_user(request, message)


@admin.action(description="Approve & email a helper login to the applicant")
def approve_and_provision_helper(modeladmin, request, queryset):
    login_url = request.build_absolute_uri(reverse("login"))
    approved, blocked = 0, 0
    for application in queryset.exclude(status=MentorApplication.APPROVED):
        if not application.has_valid_background_check:
            blocked += 1
            continue
        provision_account(HelperAccount, application.applicant_name, application.applicant_email, login_url)
        application.status = MentorApplication.APPROVED
        application.save(update_fields=["status"])
        approved += 1
    message = f"Provisioned {approved} helper account(s) and emailed their temp password."
    if blocked:
        message += f" Skipped {blocked} without a valid (non-expired) background check."
    modeladmin.message_user(request, message)


class BackgroundCheckAdminMixin:
    """Shared with both application admins: the document is on private
    storage with no public URL, so the only way to see it — even from here
    — is this permission-gated link to the protected download view."""

    def get_readonly_fields(self, request, obj=None):
        # document_link needs request.user but ModelAdmin field methods only
        # receive obj — stash the request for it to read.
        self._current_request = request
        return super().get_readonly_fields(request, obj)

    def document_link(self, obj):
        if not self._current_request.user.has_perm("applications.can_review_background_checks"):
            return "Restricted — requires the background-check reviewer permission"
        if not obj.background_check_document:
            return "No document (discarded once validated, or none uploaded)"
        url = reverse("download_background_check", kwargs={"kind": self.download_kind, "pk": obj.pk})
        return format_html('<a href="{}">Download document</a>', url)

    document_link.short_description = "Background check document"


@admin.register(DojoApplication)
class DojoApplicationAdmin(BackgroundCheckAdminMixin, admin.ModelAdmin):
    download_kind = "dojo"
    list_display = ["applicant_name", "applicant_email", "area", "status", "background_check_status", "background_check_expires_at", "submitted_at"]
    list_filter = ["status", "background_check_status"]
    readonly_fields = ["document_link"]
    actions = [request_background_check, validate_background_check, reject_background_check, approve_and_provision_owner]


@admin.register(MentorApplication)
class MentorApplicationAdmin(BackgroundCheckAdminMixin, admin.ModelAdmin):
    download_kind = "mentor"
    list_display = ["applicant_name", "applicant_email", "role", "dojo", "status", "background_check_status", "background_check_expires_at", "submitted_at"]
    list_filter = ["status", "role", "background_check_status"]
    readonly_fields = ["document_link"]
    actions = [request_background_check, validate_background_check, reject_background_check, approve_and_provision_helper]
