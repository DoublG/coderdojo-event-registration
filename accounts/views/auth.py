"""Logging in (the only way in: a password or a login link, then the second step
when the account has one), logging out, and changing or resetting a password."""

from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from two_factor.plugins.registry import registry
from two_factor.views import LoginView as TwoFactorLoginView
from two_factor.views.utils import IdempotentSessionWizardView

from core.manage_nav import manage_contexts

from .. import login_links, two_step
from ..forms import (
    ForcedPasswordChangeForm,
    LoginForm,
    LoginLinkForm,
    LoginLinkRequestForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from ..models import Ninja
from ..two_step_forms import BackupCodeForm, CodeTokenForm, PasskeyTokenForm


def _post_login_redirect(request, user):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url

    # Organisation admins, champions and mentors land in the management
    # area (/manage/ picks the organisation or their first dojo; see
    # core.manage_nav for who counts).
    if manage_contexts(user).any:
        return reverse("manage_home")

    if user.is_ninja:
        ninja = Ninja.objects.filter(account=user).first()
        return reverse("ninja_detail", kwargs={"ninja_id": ninja.id}) if ninja else reverse("home")

    return reverse("account_home")


class LoginView(TwoFactorLoginView):
    """The one login page (/login/, LOGIN_URL): django-two-factor-auth's login
    in steps. First email or username and password; an account with two-step
    login on (accounts/two_step.py) then confirms with its authenticator app,
    a passkey or a backup code, unless this browser was remembered. It must
    stay the only way in: another login route would skip the second step
    (the Django admin's login is patched to come here, TWO_FACTOR_PATCH_ADMIN).
    A lapsed background check never blocks login — it only removes dojo-team
    access (dojos.access); see the account page."""

    template_name = "accounts/login.html"
    form_list = (
        (TwoFactorLoginView.AUTH_STEP, LoginForm),
        (TwoFactorLoginView.TOKEN_STEP, CodeTokenForm),
        (TwoFactorLoginView.BACKUP_STEP, BackupCodeForm),
    )

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_post_login_redirect(request, request.user))
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, step=None, **kwargs):
        if (step or self.steps.current) == self.TOKEN_STEP:
            # The package picks its own token form for the device; pick ours.
            method = registry.method_from_device(self.get_device())
            self.form_list[self.TOKEN_STEP] = PasskeyTokenForm if method.code == "webauthn" else CodeTokenForm
            form = IdempotentSessionWizardView.get_form(self, step=step, **kwargs)
            if self.show_timeout_error:
                form.cleaned_data = getattr(form, "cleaned_data", {})
                form.add_error(None, _("That took too long. Please log in again."))
            return form
        form = super().get_form(step=step, **kwargs)
        if self.show_timeout_error:
            form.errors.pop("__all__", None)
            form.add_error(None, _("That took too long. Please log in again."))
        return form

    def get_success_url(self):
        return _post_login_redirect(self.request, self.get_user())

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        if self.steps.current == self.TOKEN_STEP:
            context["device_kind"] = two_step.kind_of(context["device"])
            context["passkey_options"] = self.request.session.get("webauthn_request_options")
            context["other_kinds"] = [
                (other.persistent_id, two_step.kind_of(other)) for other in context["other_devices"]
            ]
        return context


login = LoginView.as_view()


class LoginLinkView(LoginView):
    """A login from an emailed link (/login/link/<uidb64>/<token>/,
    accounts/login_links.py, DATA_MODEL.md §24). The same login steps as
    /login/ with another first step: GET asks "Log in as ...?" (so a mail
    scanner that follows the link logs nothing in), POST logs in, or goes
    on to the second step on this same URL when the account has two-step
    login. Someone logged in can open a link too: that's how an account
    without a password confirms it's them (accounts.reauth)."""

    form_list = (
        (TwoFactorLoginView.AUTH_STEP, LoginLinkForm),
        (TwoFactorLoginView.TOKEN_STEP, CodeTokenForm),
        (TwoFactorLoginView.BACKUP_STEP, BackupCodeForm),
    )

    def dispatch(self, request, *args, **kwargs):
        self.link_user = login_links.user_from_link(kwargs["uidb64"], kwargs["token"])
        if self.link_user is not None:
            # login() needs the backend; the wizard stores it with the account.
            self.link_user.backend = "accounts.backends.EmailOrUsernameBackend"
        # Not LoginView.dispatch: a logged-in account may log in again.
        return TwoFactorLoginView.dispatch(self, request, *args, **kwargs)

    def get_form_kwargs(self, step=None):
        if step == self.AUTH_STEP:
            return {"link_user": self.link_user}
        return super().get_form_kwargs(step)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        context["link_login"] = True
        context["link_user"] = self.link_user
        return context


login_link = LoginLinkView.as_view()


def login_link_request(request):
    """/login/link/: ask for a login link. The answer is the same whatever
    the address, so it never tells who has an account
    (login_links.request_link)."""
    if request.user.is_authenticated:
        return redirect(_post_login_redirect(request, request.user))
    form = LoginLinkRequestForm(request.POST or None)
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = ""
    if request.method == "POST" and form.is_valid():
        try:
            login_links.request_link(form.cleaned_data["email"], next_url or None)
        except login_links.LoginLinkError as error:
            form.add_error(None, error.message)
        else:
            return render(
                request,
                "accounts/login_link_request.html",
                {"sent_to": form.cleaned_data["email"], "valid_minutes": login_links.VALID_MINUTES},
            )
    return render(request, "accounts/login_link_request.html", {"form": form, "next": next_url})


@login_required
@require_POST
def login_link_reauth(request):
    """ "Mail me a confirmation link" on a page that asks to confirm it's you
    (accounts.forms.ConfirmIdentityForm), for an account without a
    password: a login link back to that page (accounts.reauth)."""
    next_url = request.POST.get("next") or ""
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse("account_security")
    error = None
    try:
        login_links.reauth_link(request.user, next_url)
    except login_links.LoginLinkError as exc:
        error = exc.message
    return render(
        request,
        "accounts/login_link_reauth.html",
        {"error": error, "next": next_url, "valid_minutes": login_links.VALID_MINUTES},
    )


def logout(request):
    auth_logout(request)
    return redirect("home")


@login_required
def change_password(request):
    """Where ForcePasswordChangeMiddleware sends anyone still on a
    temporary, admin-issued password (see applications.admin) — and also
    reachable directly by anyone who just wants to change theirs."""
    if request.user.uses_login_link:
        # No password to change: setting one is switching back (DATA_MODEL.md §24).
        return redirect("account_security_password")
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

    return render(
        request,
        "accounts/change_password.html",
        {
            "form": form,
            "forced": request.user.must_change_password,
        },
    )


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    # The mail itself: StyledPasswordResetForm.send_mail → the mail engine
    # (template "password_reset").
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
