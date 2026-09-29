"""The organisation dashboard's Volunteers pages (shell core/_manage_base.html,
DATA_MODEL.md §21): background checks (/manage/checks/) and applications
(/manage/applications/). The Volunteers area only (accounts.organisation.require_area,
the reviewer role, 404 otherwise); every decision goes
through applications.services, which deletes the document the moment a
check is decided."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.organisation import Area, require_area
from core.audit import log_access

from . import services
from .forms import BackgroundCheckDecisionForm
from .models import Application

EXPIRING_WITHIN = timedelta(days=30)
SEARCH_LIMIT = 50


def _with_applications(accounts):
    return accounts.prefetch_related("applications")


@login_required
def check_list(request):
    """The reviewers' work queue: documents to review first, then checks
    waiting for a document, expired ones and those that expire soon."""
    require_area(request, Area.VOLUNTEERS)
    now = timezone.now()
    checks = _with_applications(User.objects.exclude(background_check_status=User.CHECK_NOT_REQUESTED))
    query = request.GET.get("q", "").strip()
    found = None
    if query:
        found = checks.filter(
            Q(email__icontains=query)
            | Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        ).order_by("last_name", "first_name", "username")[:SEARCH_LIMIT]
    validated = checks.filter(background_check_status=User.CHECK_VALIDATED)
    return render(
        request,
        "applications/manage/check_list.html",
        {
            "query": query,
            "found": found,
            "search_limit": SEARCH_LIMIT,
            "awaiting": checks.filter(background_check_status=User.CHECK_SUBMITTED).order_by(
                "background_check_submitted_at"
            ),
            "waiting": checks.filter(background_check_status__in=[User.CHECK_REQUESTED, User.CHECK_REJECTED]).order_by(
                "background_check_requested_at"
            ),
            "expired": validated.filter(background_check_expires_at__lte=now).order_by("-background_check_expires_at"),
            "expiring": validated.filter(
                background_check_expires_at__gt=now, background_check_expires_at__lte=now + EXPIRING_WITHIN
            ).order_by("background_check_expires_at"),
            "active": "checks",
        },
    )


@login_required
def check_detail(request, user_id):
    """One account's check: what they applied for, the earlier decisions, the
    document while there is one, and the decision. Recorded as a view in the
    audit log: it shows criminal-record data (DATA_MODEL.md §14)."""
    require_area(request, Area.VOLUNTEERS)
    account = get_object_or_404(User, pk=user_id, account_type=User.ADULT)
    log_access(account)
    return render(
        request,
        "applications/manage/check_detail.html",
        {
            "account": account,
            "applications": account.applications.all(),
            "history": account.background_check_history.select_related("reviewed_by"),
            "form": BackgroundCheckDecisionForm(),
            "is_self": account.pk == request.user.pk,
            "can_request": not account.background_check_valid
            and account.background_check_status != User.CHECK_SUBMITTED,
            "active": "checks",
        },
    )


@login_required
@require_POST
def check_decide(request, user_id):
    require_area(request, Area.VOLUNTEERS)
    account = get_object_or_404(User, pk=user_id, account_type=User.ADULT)
    form = BackgroundCheckDecisionForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Choose Validate or Reject."))
        return redirect("manage_check_detail", user_id=account.pk)
    note = form.cleaned_data["note"]
    try:
        if form.cleaned_data["decision"] == BackgroundCheckDecisionForm.VALIDATE:
            services.validate_background_check(account, request.user, note)
            messages.success(request, _("Validated. The document has been deleted."))
        else:
            services.reject_background_check(account, request.user, note)
            messages.success(
                request,
                _("Rejected. The document has been deleted and %(name)s has been told.")
                % {"name": account.get_full_name() or account.username},
            )
    except services.OnboardingError as error:
        messages.error(request, str(error))
        return redirect("manage_check_detail", user_id=account.pk)
    return redirect("manage_check_list")


@login_required
@require_POST
def check_request(request, user_id):
    """Ask for a (new) document: a first check, a renewal after expiry, or
    the upload link again."""
    require_area(request, Area.VOLUNTEERS)
    account = get_object_or_404(User, pk=user_id, account_type=User.ADULT)
    try:
        services.request_background_check(account, request)
    except services.OnboardingError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("The upload link has been sent to %(email)s.") % {"email": account.email})
    # The queue's "Send the link again" comes back to the queue.
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("manage_check_detail", user_id=account.pk)


# --- applications ------------------------------------------------------------------


STATUS_FILTERS = [Application.PENDING, Application.APPROVED, Application.REJECTED]


@login_required
def application_list(request):
    require_area(request, Area.VOLUNTEERS)
    status = request.GET.get("status", Application.PENDING)
    kind = request.GET.get("kind", "")
    applications = Application.objects.select_related("account", "dojo").order_by("submitted_at")
    if status in STATUS_FILTERS:
        applications = applications.filter(status=status)
    if kind in dict(Application.KIND_CHOICES):
        applications = applications.filter(kind=kind)
    return render(
        request,
        "applications/manage/application_list.html",
        {
            "applications": applications,
            "status": status,
            "kind": kind,
            "status_choices": Application.STATUS_CHOICES,
            "kind_choices": Application.KIND_CHOICES,
            "active": "applications",
        },
    )


@login_required
def application_detail(request, application_id):
    require_area(request, Area.VOLUNTEERS)
    application = get_object_or_404(Application.objects.select_related("account", "dojo"), pk=application_id)
    account = application.account
    return render(
        request,
        "applications/manage/application_detail.html",
        {
            "application": application,
            "account": account,
            "is_self": account.pk == request.user.pk,
            "can_request": not account.background_check_valid
            and account.background_check_status != User.CHECK_SUBMITTED,
            "active": "applications",
        },
    )


@login_required
@require_POST
def application_decide(request, application_id):
    require_area(request, Area.VOLUNTEERS)
    application = get_object_or_404(Application.objects.select_related("account", "dojo"), pk=application_id)
    action = request.POST.get("action")
    try:
        if action == "approve":
            services.approve_application(application, request.user)
            messages.success(request, _("Approved. %(name)s has been told.") % {"name": _name(application.account)})
        elif action == "reject":
            services.reject_application(application, request.user)
            messages.success(request, _("Rejected. %(name)s has been told.") % {"name": _name(application.account)})
        else:
            messages.error(request, _("Choose Approve or Reject."))
    except services.OnboardingError as error:
        messages.error(request, str(error))
    return redirect("manage_application_detail", application_id=application.pk)


def _name(account):
    return account.get_full_name() or account.username
