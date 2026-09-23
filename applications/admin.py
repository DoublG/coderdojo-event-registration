from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from accounts.models import DojoOwner, HelperAccount
from accounts.provisioning import attach_role, provision_account
from dojos.models import Mentor

from .models import BACKGROUND_CHECK_VALIDITY, BackgroundCheckMixin, DojoApplication, MentorApplication
from .services import send_background_check_request, send_role_activated_email


def _linked_account(application):
    """The DojoOwner/HelperAccount this application already provisioned, if
    any (set by approve_and_provision_owner/helper) — present once the
    applicant is a real, logged-in account rather than still pending
    approval, which is exactly when a background-check *renewal* (as
    opposed to the original one) needs to sync back onto the account that
    actually gates login. Works across both DojoApplication.provisioned_owner
    and MentorApplication.provisioned_helper without the caller needing to
    know which one applies."""
    return getattr(application, "provisioned_owner", None) or getattr(application, "provisioned_helper", None)


@admin.action(description="Request background check document from applicant")
def request_background_check(modeladmin, request, queryset):
    # Not excluding by status: a currently-valid check needs no action, but
    # one that's VALIDATED yet expired (or about to expire) is exactly the
    # renewal case — re-running this on the same row is how that's requested.
    sent = 0
    for application in queryset:
        if application.has_valid_background_check:
            continue
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

        # Renewal case: this application already has a live account
        # (see _linked_account) — sync the fresh expiry onto it so
        # accounts.User.background_check_valid (and BackgroundCheckMiddleware)
        # see it as vetted again immediately, without waiting on a re-approval.
        account = _linked_account(application)
        if account is not None:
            account.background_check_expires_at = application.background_check_expires_at
            account.save(update_fields=["background_check_expires_at"])
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


def _provision_or_promote(application, account_model, role_label, login_url):
    """Shared by approve_and_provision_owner/helper. If the applicant was already logged in when
    they applied (application.applicant_account set — e.g. a Guardian applying to also become a
    DojoOwner/HelperAccount), promote that existing account in place via attach_role instead of
    provisioning a disconnected new login, and tell them about the new role rather than emailing
    a temp password they don't need. Otherwise, today's anonymous-applicant path is unchanged."""
    if application.applicant_account_id is not None:
        account = attach_role(application.applicant_account, account_model)
        send_role_activated_email(application, role_label)
    else:
        account = provision_account(account_model, application.applicant_name, application.applicant_email, login_url)
    return account


def _apply_background_check(account, application):
    """From here on it's the account, not the application, that
    accounts.User.background_check_valid / BackgroundCheckMiddleware check
    on every login and request. An account approved for a second dojo
    (another application) keeps whichever check expires last, so approving
    an application whose check is older never shortens it."""
    expiries = [e for e in (account.background_check_expires_at, application.background_check_expires_at) if e]
    account.background_check_required = True
    account.background_check_expires_at = max(expiries) if expiries else None
    account.save(update_fields=["background_check_required", "background_check_expires_at"])


@admin.action(description="Approve & email a DojoOwner login to the applicant")
def approve_and_provision_owner(modeladmin, request, queryset):
    login_url = request.build_absolute_uri(reverse("login"))
    approved, blocked = 0, 0
    for application in queryset.exclude(status=DojoApplication.APPROVED):
        if not application.has_valid_background_check:
            blocked += 1
            continue
        account = _provision_or_promote(application, DojoOwner, "dojo owner", login_url)
        _apply_background_check(account, application)
        application.status = DojoApplication.APPROVED
        application.provisioned_owner = account
        application.save(update_fields=["status", "provisioned_owner"])
        approved += 1
    message = f"Provisioned/updated {approved} DojoOwner account(s)."
    if blocked:
        message += f" Skipped {blocked} without a valid (non-expired) background check."
    modeladmin.message_user(request, message)


def _link_helper_to_dojo(application, account):
    """An application for a specific dojo gets the new helper a Mentor
    profile at that dojo — the link dojos.access uses to open that dojo's
    admin area to them. Kept off the public team pages (is_public=False)
    until someone opts them in. A helper can help at several dojos (one
    profile each), so this only skips when the application is open to any
    dojo or they already have a profile at this one."""
    if application.dojo_id is None or Mentor.objects.filter(helper_account=account, dojo_id=application.dojo_id).exists():
        return
    Mentor.objects.create(
        name=application.applicant_name,
        dojo_id=application.dojo_id,
        role=Mentor.VOLUNTEER,
        email=application.applicant_email,
        helper_account=account,
        is_public=False,
    )


@admin.action(description="Approve & email a helper login to the applicant")
def approve_and_provision_helper(modeladmin, request, queryset):
    login_url = request.build_absolute_uri(reverse("login"))
    approved, blocked = 0, 0
    for application in queryset.exclude(status=MentorApplication.APPROVED):
        if not application.has_valid_background_check:
            blocked += 1
            continue
        account = _provision_or_promote(application, HelperAccount, "helper", login_url)
        _apply_background_check(account, application)
        application.status = MentorApplication.APPROVED
        application.provisioned_helper = account
        application.save(update_fields=["status", "provisioned_helper"])
        _link_helper_to_dojo(application, account)
        approved += 1
    message = f"Provisioned/updated {approved} helper account(s)."
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
