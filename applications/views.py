from django.contrib.auth.decorators import permission_required
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


def register_dojo(request):
    submitted = False
    if request.method == "POST":
        form = DojoApplicationForm(request.POST)
        if form.is_valid():
            form.save()
            submitted = True
            form = DojoApplicationForm()
    else:
        form = DojoApplicationForm()

    return render(request, "applications/register_dojo.html", {"form": form, "submitted": submitted})


def register_helper(request):
    submitted = False
    if request.method == "POST":
        form = MentorApplicationForm(request.POST)
        if form.is_valid():
            form.save()
            submitted = True
            form = MentorApplicationForm()
    else:
        form = MentorApplicationForm()

    return render(request, "applications/register_helper.html", {"form": form, "submitted": submitted})


def upload_background_check(request, token):
    """No login required — applicants aren't authenticated users yet at this
    stage, they just hold the emailed link built from background_check_token."""
    application = _find_application_by_token(token)
    if application is None:
        raise Http404

    already_submitted = application.background_check_status in (
        BackgroundCheckMixin.SUBMITTED, BackgroundCheckMixin.VALIDATED,
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

    return render(request, "applications/upload_background_check.html", {
        "application": application,
        "form": form,
        "submitted": submitted,
        "already_submitted": already_submitted,
    })


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
