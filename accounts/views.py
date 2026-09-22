from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from events.models import Registration

from .forms import ForcedPasswordChangeForm, LoginForm, StyledPasswordResetForm, StyledSetPasswordForm
from .models import Guardian, Participant


def _get_own_guardian(request, guardian_id):
    """A Guardian's own pages (account overview, cancelling a
    registration): 404s rather than 403s for a mismatch, so a guessed id
    doesn't even confirm another family's account exists."""
    guardian = get_object_or_404(Guardian, id=guardian_id)
    if guardian.pk != request.user.pk:
        raise Http404
    return guardian


def _post_login_redirect(request, user):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url

    dojo_owner = getattr(user, "dojoowner", None)
    if dojo_owner is not None:
        first_dojo = dojo_owner.dojos.first()
        if first_dojo is not None:
            return reverse("dojo_dashboard", kwargs={"dojo_id": first_dojo.id})

    guardian = getattr(user, "guardian", None)
    if guardian is not None:
        return reverse("guardian_detail", kwargs={"guardian_id": guardian.id})

    child_account = getattr(user, "childaccount", None)
    if child_account is not None and hasattr(child_account, "participant"):
        participant = child_account.participant
        if participant.guardian_id:
            return reverse("child_detail", kwargs={"guardian_id": participant.guardian_id, "child_id": participant.id})

    return reverse("home")


def login(request):
    if request.user.is_authenticated:
        return redirect(_post_login_redirect(request, request.user))

    error = None
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            if user is not None:
                auth_login(request, user)
                return redirect(_post_login_redirect(request, user))
            error = "That email/password combination doesn't match an account."
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form, "error": error})


def logout(request):
    auth_logout(request)
    return redirect("home")


@login_required
def change_password(request):
    """Where ForcePasswordChangeMiddleware sends anyone still on a
    temporary, admin-issued password (see applications.admin) — and also
    reachable directly by anyone who just wants to change theirs."""
    if request.method == "POST":
        form = ForcedPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.must_change_password = False
            user.save()
            update_session_auth_hash(request, user)  # keep them logged in
            return redirect(_post_login_redirect(request, user))
    else:
        form = ForcedPasswordChangeForm(request.user)

    return render(request, "accounts/change_password.html", {
        "form": form, "forced": request.user.must_change_password,
    })


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    form_class = StyledPasswordResetForm


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """Like the base view, but a self-service reset also counts as
    "setting your own password" — clears must_change_password so someone
    who forgot their admin-issued temp password isn't immediately forced
    through change_password again right after."""

    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")
    form_class = StyledSetPasswordForm

    def form_valid(self, form):
        response = super().form_valid(form)
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        return response


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


def register(request):
    return render(request, "accounts/register.html")


def register_guardian(request):
    return render(request, "accounts/register_guardian.html")


def _children_context(guardian):
    now = timezone.now()
    children = []
    for child in guardian.children.all():
        # Not filtering on waiting_list — a waitlisted registration is
        # still "what's coming up" for this child, just flagged as such
        # in the template (see the cd-badge--warning next to it).
        next_registration = (
            child.registration_set.filter(event__start_time__gte=now)
            .select_related("event")
            .order_by("event__start_time")
            .first()
        )
        children.append({"child": child, "next_registration": next_registration})
    return children


@login_required
def guardian_detail(request, guardian_id):
    guardian = _get_own_guardian(request, guardian_id)
    children = _children_context(guardian)
    return render(request, "accounts/guardian_detail.html", {"guardian": guardian, "children": children})


@login_required
def add_child(request, guardian_id):
    """The "+ Add a child" widget on the account page (see
    accounts/partials/_children_list.html) — posts here via htmx and
    swaps in the freshly rendered list, so the page updates without a
    full reload."""
    guardian = _get_own_guardian(request, guardian_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            Participant.objects.create(
                guardian=guardian, name=name, date_of_birth=request.POST.get("date_of_birth") or None,
            )
    children = _children_context(guardian)
    return render(request, "accounts/partials/_children_list.html", {"guardian": guardian, "children": children})


@login_required
def child_detail(request, guardian_id, child_id):
    guardian = _get_own_guardian(request, guardian_id)
    child = get_object_or_404(Participant, id=child_id, guardian=guardian)
    now = timezone.now()
    history = (
        child.registration_set.filter(event__start_time__lt=now)
        .select_related("event", "event__dojo", "event__mentor")
        .order_by("-event__start_time")
    )
    return render(request, "accounts/child_detail.html", {"child": child, "history": history})


@login_required
def cancel_registration(request, guardian_id, registration_id):
    guardian = _get_own_guardian(request, guardian_id)
    registration = get_object_or_404(Registration, id=registration_id, participant__guardian=guardian)

    if request.method == "POST":
        event = registration.event
        was_confirmed = not registration.waiting_list
        registration.delete()

        if was_confirmed:
            # Cancelling a confirmed spot opens one up — promote whoever's
            # been waiting longest for *this* event (see Registration.position,
            # the FCFS queue events.views.event_signup assigns on signup).
            next_in_line = Registration.objects.filter(event=event, waiting_list=True).order_by("position").first()
            if next_in_line:
                next_in_line.waiting_list = False
                next_in_line.save(update_fields=["waiting_list"])

    return redirect("guardian_detail", guardian_id=guardian.id)
