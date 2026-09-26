from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _

from accounts.models import User
from core.audit import log_access

from . import services
from .forms import BackgroundCheckUploadForm, ChampionApplicationForm, MentorApplicationForm
from .models import Application


def _apply(request, kind, form_class, template):
    """Shared by both application kinds: applying requires being logged in
    (the application belongs to the account), and there's one pending or
    approved application per account and kind."""
    if request.user.is_ninja:
        raise Http404
    submitted = False
    error = None
    form = form_class(account=request.user)
    if request.user.applications.filter(kind=kind, status__in=[Application.PENDING, Application.APPROVED]).exists():
        error = _("You've already applied for this — see your account page for its status.")
    elif request.method == "POST":
        form = form_class(request.POST, account=request.user)
        if form.is_valid():
            fields = {name: value for name, value in form.cleaned_data.items() if name != "phone"}
            try:
                services.submit_application(request.user, kind, **fields)
            except services.OnboardingError as exc:
                error = str(exc)
            else:
                if form.cleaned_data["phone"] != request.user.phone:
                    request.user.phone = form.cleaned_data["phone"]
                    request.user.save(update_fields=["phone"])
                submitted = True
    return render(request, template, {"form": form, "submitted": submitted, "error": error})


@login_required
def register_dojo(request):
    """Apply to become a champion (start a dojo)."""
    return _apply(request, Application.CHAMPION, ChampionApplicationForm, "applications/register_dojo.html")


@login_required
def register_helper(request):
    """Apply to become a mentor."""
    return _apply(request, Application.MENTOR, MentorApplicationForm, "applications/register_helper.html")


def _upload_context(request, account):
    """Shared by the emailed-link upload page and the logged-in one."""
    submitted = False
    form = BackgroundCheckUploadForm()
    if request.method == "POST" and account.background_check_can_upload:
        form = BackgroundCheckUploadForm(request.POST, request.FILES)
        if form.is_valid():
            services.submit_background_check(account, form.cleaned_data["document"])
            submitted = True
    return {
        "account": account,
        "form": form,
        "submitted": submitted,
        "already_submitted": not submitted and not account.background_check_can_upload,
    }


def upload_background_check(request, token):
    """No login required: the account holder follows the emailed link built
    from their background_check_token (set when a check is requested)."""
    account = get_object_or_404(User, background_check_token=token)
    return render(request, "applications/upload_background_check.html", _upload_context(request, account))


@login_required
def renew_background_check(request):
    """The same upload, for the logged-in account itself — linked from the
    account page when a check is requested, was rejected, or has expired."""
    return render(request, "applications/upload_background_check.html", _upload_context(request, request.user))


@permission_required("applications.can_review_background_checks", raise_exception=True)
def download_background_check(request, user_id):
    """The only way to read a background-check document. It's stored on
    private storage (no public media URL at all), so this permission check is
    the sole gate — not obscurity. The file is deleted as soon as a decision
    is made (applications.services), so this 404s for anything decided."""
    account = get_object_or_404(User, pk=user_id)
    if not account.background_check_document:
        raise Http404
    log_access(account)  # a criminal-record extract (GDPR art. 10): recorded in the audit log
    return FileResponse(
        account.background_check_document.open("rb"),
        as_attachment=True,
        filename=account.background_check_document.name.rsplit("/", 1)[-1],
    )
