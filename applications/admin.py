from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from accounts.models import User
from core.audit import LogAccessAdminMixin

from . import services
from .models import Application, BackgroundCheck, BackgroundCheckHistory

REVIEW_PERMISSION = "applications.can_review_background_checks"


def _run(modeladmin, request, queryset, action, done_label):
    done, errors = 0, []
    for obj in queryset:
        try:
            action(obj)
            done += 1
        except services.OnboardingError as exc:
            errors.append(str(exc))
    modeladmin.message_user(request, f"{done_label}: {done}.")
    for error in errors:
        modeladmin.message_user(request, error, level="warning")


# --- applications -------------------------------------------------------------------
# Every action needs change permission: without it Django offers an action
# to anyone who can merely view the list (e.g. the board's read-only
# organisation role, accounts.organisation).

@admin.action(description="Request a background check from the applicant", permissions=["change"])
def request_check_for_applicants(modeladmin, request, queryset):
    _run(modeladmin, request, queryset,
         lambda application: services.request_background_check(application.account, request),
         "Background check requested")


@admin.action(description="Approve (needs a valid background check)", permissions=["change"])
def approve_applications(modeladmin, request, queryset):
    _run(modeladmin, request, queryset,
         lambda application: services.approve_application(application, request.user), "Approved")


@admin.action(description="Reject", permissions=["change"])
def reject_applications(modeladmin, request, queryset):
    _run(modeladmin, request, queryset,
         lambda application: services.reject_application(application, request.user), "Rejected")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["account", "kind", "status", "dojo", "area", "check_status", "submitted_at", "decided_by"]
    list_filter = ["kind", "status", "account__background_check_status"]
    search_fields = ["account__username", "account__email", "account__first_name", "account__last_name", "area"]
    readonly_fields = ["account", "submitted_at", "decided_by", "decided_at", "check_status"]
    actions = [request_check_for_applicants, approve_applications, reject_applications]

    @admin.display(description="Background check")
    def check_status(self, obj):
        account = obj.account
        if account.background_check_valid:
            return f"Valid until {account.background_check_expires_at:%d/%m/%Y}"
        return account.get_background_check_status_display()


# --- background checks (on the account) ----------------------------------------------

class BackgroundCheckHistoryInline(admin.TabularInline):
    """The append-only audit log: who decided, when. Read-only."""

    model = BackgroundCheckHistory
    fk_name = "account"
    extra = 0
    can_delete = False
    fields = ["decision", "reviewed_by", "reviewed_at", "requested_at", "submitted_at", "expires_at", "note"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.action(description="Request a (new) background check document", permissions=["change"])
def request_checks(modeladmin, request, queryset):
    _run(modeladmin, request, queryset, lambda user: services.request_background_check(user, request),
         "Background check requested")


@admin.action(description="Validate the uploaded document (deletes it)")
def validate_checks(modeladmin, request, queryset):
    if not request.user.has_perm(REVIEW_PERMISSION):
        modeladmin.message_user(request, "You don't have permission to review background checks.", level="error")
        return
    _run(modeladmin, request, queryset, lambda user: services.validate_background_check(user, request.user),
         "Validated (documents deleted)")


@admin.action(description="Reject the uploaded document (deletes it)")
def reject_checks(modeladmin, request, queryset):
    if not request.user.has_perm(REVIEW_PERMISSION):
        modeladmin.message_user(request, "You don't have permission to review background checks.", level="error")
        return
    _run(modeladmin, request, queryset, lambda user: services.reject_background_check(user, request.user),
         "Rejected (documents deleted)")


@admin.register(BackgroundCheckHistory)
class BackgroundCheckHistoryAdmin(admin.ModelAdmin):
    """The decision log, append-only in normal use (applications.services).
    Editable here only for fixing something by hand."""

    list_display = ["account", "decision", "reviewed_by", "reviewed_at", "expires_at"]
    list_filter = ["decision"]
    search_fields = ["account__username", "account__email"]


@admin.register(BackgroundCheck)
class BackgroundCheckAdmin(LogAccessAdminMixin, admin.ModelAdmin):
    """Reviewers' list of accounts with a background check in progress or on
    record. The document is on private storage with no public URL: the only
    way to see it — even from here — is the permission-gated download link."""

    list_display = ["username", "email", "background_check_status", "background_check_submitted_at", "background_check_expires_at"]
    list_filter = ["background_check_status"]
    search_fields = ["username", "email", "first_name", "last_name"]
    fields = [
        "username", "email", "background_check_status", "background_check_requested_at",
        "background_check_submitted_at", "background_check_reviewed_at", "background_check_expires_at",
        "document_link",
    ]
    readonly_fields = fields
    inlines = [BackgroundCheckHistoryInline]
    actions = [request_checks, validate_checks, reject_checks]

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(background_check_status=User.CHECK_NOT_REQUESTED)

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        # document_link needs request.user but ModelAdmin field methods only
        # receive obj — stash the request for it to read.
        self._current_request = request
        return super().get_readonly_fields(request, obj)

    @admin.display(description="Document")
    def document_link(self, obj):
        if not self._current_request.user.has_perm(REVIEW_PERMISSION):
            return "Restricted — requires the background-check reviewer permission"
        if not obj.background_check_document:
            return "No document (deleted once decided, or none uploaded)"
        url = reverse("download_background_check", kwargs={"user_id": obj.pk})
        return format_html('<a href="{}">Download document</a>', url)
