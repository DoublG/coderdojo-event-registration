from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.utils import timezone

from .forms import BackgroundCheckUploadForm, DojoApplicationForm, MentorApplicationForm
from .models import BackgroundCheckMixin, DojoApplication, MentorApplication

APPLICATION_MODELS_BY_KIND = {"dojo": DojoApplication, "mentor": MentorApplication}


def _find_application_by_token(token):
    for model in APPLICATION_MODELS_BY_KIND.values():
        application = model.objects.filter(background_check_token=token).first()
        if application is not None:
            return application
    return None


def _find_application_for_account(user):
    """The application a logged-in DojoOwner/HelperAccount was provisioned
    from (DojoApplication.provisioned_owner / MentorApplication.provisioned_helper),
    for renew_background_check — the counterpart to _find_application_by_token
    for someone who's already authenticated rather than holding an emailed link."""
    dojo_owner = getattr(user, "dojoowner", None)
    if dojo_owner is not None:
        return getattr(dojo_owner, "application", None)
    helper_account = getattr(user, "helperaccount", None)
    if helper_account is not None:
        return getattr(helper_account, "application", None)
    return None


def _upload_background_check_context(request, application):
    """Shared by upload_background_check (emailed token link, no login) and
    renew_background_check (logged-in account whose check has lapsed —
    accounts.middleware.BackgroundCheckMiddleware) — both just accept a
    document against an already-resolved application, on the same template."""
    # A VALIDATED check that's since expired is exactly the renewal case —
    # only a *currently* valid one (or one already awaiting review) blocks
    # a fresh upload.
    already_submitted = (
        application.background_check_status == BackgroundCheckMixin.SUBMITTED
        or application.has_valid_background_check
    )
    submitted = False
    if request.method == "POST" and not already_submitted:
        form = BackgroundCheckUploadForm(request.POST, request.FILES)
        if form.is_valid():
            application.background_check_document = form.cleaned_data["document"]
            application.background_check_status = BackgroundCheckMixin.SUBMITTED
            application.background_check_submitted_at = timezone.now()
            application.save(update_fields=[
                "background_check_document", "background_check_status", "background_check_submitted_at",
            ])
            submitted = True
    else:
        form = BackgroundCheckUploadForm()

    return {
        "application": application,
        "form": form,
        "submitted": submitted,
        "already_submitted": already_submitted,
    }


def _applicant_initial(user):
    """Prefill for register_dojo/register_helper when the applicant is already logged in (e.g. a
    Guardian applying to also become a DojoOwner/HelperAccount). Django's auth always loads
    `user` as the base accounts.User row, never a role subclass (see accounts.context_processors.
    user_roles for the same pattern) — phone only exists on Guardian, so it's only there via the
    reverse one-to-one accessor, not directly on `user`."""
    guardian = getattr(user, "guardian", None)
    return {
        "applicant_name": f"{user.first_name} {user.last_name}".strip() or user.get_username(),
        "applicant_email": user.email,
        "applicant_phone": guardian.phone if guardian is not None else "",
    }


def register_dojo(request):
    submitted = False
    if request.method == "POST":
        form = DojoApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            if request.user.is_authenticated:
                application.applicant_account = request.user
            application.save()
            submitted = True
            form = DojoApplicationForm()
    else:
        initial = _applicant_initial(request.user) if request.user.is_authenticated else None
        form = DojoApplicationForm(initial=initial)

    return render(request, "applications/register_dojo.html", {"form": form, "submitted": submitted})


def register_helper(request):
    submitted = False
    if request.method == "POST":
        form = MentorApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            if request.user.is_authenticated:
                application.applicant_account = request.user
            application.save()
            submitted = True
            form = MentorApplicationForm()
    else:
        initial = _applicant_initial(request.user) if request.user.is_authenticated else None
        form = MentorApplicationForm(initial=initial)

    return render(request, "applications/register_helper.html", {"form": form, "submitted": submitted})


def upload_background_check(request, token):
    """No login required — applicants aren't authenticated users yet at this
    stage, they just hold the emailed link built from background_check_token."""
    application = _find_application_by_token(token)
    if application is None:
        raise Http404
    context = _upload_background_check_context(request, application)
    return render(request, "applications/upload_background_check.html", context)


@login_required
def renew_background_check(request):
    """Where BackgroundCheckMiddleware sends a logged-in DojoOwner/HelperAccount
    whose background check has lapsed: the same upload flow as
    upload_background_check, but the application is resolved from the
    authenticated account instead of an emailed token link, so there's no
    need to wait on (or re-send) that email to renew."""
    application = _find_application_for_account(request.user)
    if application is None:
        raise Http404
    context = _upload_background_check_context(request, application)
    return render(request, "applications/upload_background_check.html", context)


@permission_required("applications.can_review_background_checks", raise_exception=True)
def download_background_check(request, kind, pk):
    """The only way to read a background-check document. It's stored on
    private_storage (no public media URL at all), so this permission check
    is the sole gate — not obscurity. Once an application is validated the
    file is deleted (see applications.admin.validate_background_check), so
    this 404s for anything already decided."""
    model = APPLICATION_MODELS_BY_KIND.get(kind)
    if model is None:
        raise Http404
    application = model.objects.filter(pk=pk).first()
    if application is None or not application.background_check_document:
        raise Http404
    return FileResponse(
        application.background_check_document.open("rb"),
        as_attachment=True,
        filename=application.background_check_document.name.rsplit("/", 1)[-1],
    )
