from auditlog.context import set_actor
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST
from two_factor.plugins.registry import registry
from two_factor.views import LoginView as TwoFactorLoginView
from two_factor.views.utils import IdempotentSessionWizardView

from core.image_library import use_library_image
from core.manage_nav import manage_contexts
from dojos.team import notify_managers
from events.models import Registration, RegistrationCancellation
from mailing.automated import waitlist_promoted_mail
from mailing.categories import MailCategory
from mailing.models import ConsentEvent
from mailing.preferences import set_preference

from . import child_accounts, email_change, home_dojo, login_links, two_step
from .consent import consent_fields
from .forms import (
    AddChildForm,
    ChangeEmailForm,
    ChildAvatarForm,
    ChildEmailChangeForm,
    ChildLoginForm,
    ChildRowsFormSet,
    ConfirmIdentityForm,
    EditAccountForm,
    EditChildForm,
    ForcedPasswordChangeForm,
    LoginForm,
    LoginLinkForm,
    LoginLinkRequestForm,
    RegisterGuardianForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from .models import Guardianship, Ninja, User
from .provisioning import unique_username
from .template_avatars import TEMPLATE_KID_AVATARS
from .two_step_forms import BackupCodeForm, CodeTokenForm, PasskeyTokenForm

# Small on purpose — small enough that most children's award shelf
# actually spans more than one page, so the lazy-load carousel (same
# pattern as the homepage's "Upcoming sessions", see
# events.views.upcoming_sessions_widget) has something to demonstrate.
BADGES_PAGE_SIZE = 4


def _get_own_ninja(request, ninja_id, allow_self=False):
    """A ninja the logged-in account is a guardian of — or, with
    allow_self, the ninja's own login looking at their own page. 404s
    rather than 403s on a mismatch, so a guessed id doesn't even confirm
    another family's child exists."""
    ninja = get_object_or_404(Ninja, id=ninja_id)
    is_guardian = ninja.guardianships.filter(guardian=request.user).exists()
    is_self = allow_self and ninja.account_id == request.user.pk
    if not (is_guardian or is_self):
        raise Http404
    return ninja


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


def register(request):
    return render(request, "accounts/register.html")


def _create_ninjas(parent, children, consent=False):
    for child_form in children.forms:
        Guardianship.objects.create(guardian=parent, ninja=child_form.save(), **consent_fields(consent))


def _site_language(request):
    """The LANGUAGES code of the language the page is shown in, as the
    default for a new account's mail language."""
    codes = [code for code, _name in settings.LANGUAGES]
    current = (getattr(request, "LANGUAGE_CODE", "") or "").lower()
    return next((code for code in codes if code == current), None) or next(
        (code for code in codes if code.split("-")[0] == current.split("-")[0]), codes[0]
    )


def register_guardian(request):
    """Family sign-up for someone without an account. Already logged in?
    Any adult account can add its children from the account page, so
    there's nothing to register."""
    if request.user.is_authenticated:
        return redirect("account_home")

    if request.method == "POST":
        form = RegisterGuardianForm(request.POST)
        children = ChildRowsFormSet(request.POST)
        if all([form.is_valid(), children.is_valid()]):
            first_name, _sep, last_name = form.cleaned_data["name"].partition(" ")
            parent = User(
                username=unique_username(slugify(form.cleaned_data["name"])),
                email=form.cleaned_data["email"],
                first_name=first_name,
                last_name=last_name,
                phone=form.cleaned_data["phone"],
                postal_code=form.cleaned_data["postal_code"],
                preferred_language=form.cleaned_data["preferred_language"] or _site_language(request),
            )
            if form.uses_link:
                parent.login_method = User.LOGIN_LINK
                parent.set_unusable_password()
            else:
                parent.set_password(form.cleaned_data["password"])
            # A child never exists without a guardian: all or nothing.
            with transaction.atomic():
                parent.save()
                _create_ninjas(parent, children, consent=form.cleaned_data["child_data_mail"])
                if form.cleaned_data["newsletter"]:
                    set_preference(parent, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)

            if form.uses_link:
                # Not logged in yet: opening the first link is the first
                # login, and proves the address (DATA_MODEL.md §24).
                login_links.send_login_link(parent, first=True)
                return render(
                    request,
                    "accounts/register_check_inbox.html",
                    {"email": parent.email, "valid_days": login_links.FIRST_LINK_VALID_DAYS},
                )
            auth_login(request, parent, backend="accounts.backends.EmailOrUsernameBackend")
            return redirect("account_home")
    else:
        form = RegisterGuardianForm(initial={"preferred_language": _site_language(request)})
        children = ChildRowsFormSet()

    return render(request, "accounts/register_guardian.html", {"form": form, "children": children})


def _children_context(parent):
    now = timezone.now()
    children = []
    for child in Ninja.objects.of_guardian(parent).select_related("account").prefetch_related("belts__belt"):
        # All upcoming registrations, not just the nearest one — a child
        # can be signed up for more than one session at a time. Not
        # filtering on waiting_list either — a waitlisted registration is
        # still "what's coming up" for this child, just flagged as such
        # in the template (see the cd-badge--warning next to it).
        registrations = list(
            child.registration_set.filter(event__start_time__gte=now)
            .select_related("event")
            .order_by("event__start_time")
        )
        children.append({"child": child, "registrations": registrations})
    return children


@login_required
def account_home(request):
    """The logged-in account's own page: their ninjas and what's coming up.
    Any adult account has one (children are optional); a ninja's own login
    is sent to its ninja page instead."""
    if request.user.is_ninja:
        return redirect(_post_login_redirect(request, request.user))
    return _render_account_home(request)


def _render_account_home(request, details_form=None):
    """The account page; with `details_form`, its details are shown as that
    form (edit_account without htmx)."""
    children = _children_context(request.user)
    applications = list(request.user.applications.all())
    active_kinds = {a.kind for a in applications if a.status != "rejected"}
    return render(
        request,
        "accounts/guardian_detail.html",
        {
            "guardian": request.user,
            "form": details_form,
            "children": children,
            "add_child_form": AddChildForm(guardian=request.user),
            "applications": applications,
            "has_champion_application": "champion" in active_kinds,
            "has_mentor_application": "mentor" in active_kinds,
            "two_step_on": two_step.is_on(request.user),
        },
    )


@login_required
def edit_account(request):
    """Click-to-edit for the account page's details (see
    partials/_account_details_display.html), the same shape as edit_ninja:
    GET swaps the details for a small inline form over htmx, POST saves them
    and swaps back. Always the logged-in account's own details; a ninja's
    own login has no account page, so it gets a 404. Without htmx (no
    JavaScript) it shows the whole account page with the form open, and a
    saved form goes back to it."""
    if request.user.is_ninja:
        raise Http404
    is_htmx = request.headers.get("HX-Request") == "true"
    # A copy: validating writes the posted values onto the instance, and an
    # invalid post mustn't change request.user for the rest of the page.
    form = EditAccountForm(request.POST or None, instance=User.objects.get(pk=request.user.pk))
    if request.method == "POST" and form.is_valid():
        account = form.save()
        if not is_htmx:
            messages.success(request, _("Your details are saved."))
            return redirect("account_home")
        return render(request, "accounts/partials/_account_details_display.html", {"guardian": account})
    if not is_htmx:
        return _render_account_home(request, details_form=form)
    return render(request, "accounts/partials/_account_details_edit.html", {"guardian": request.user, "form": form})


@login_required
def change_email(request):
    """The family changes its own email address (DATA_MODEL.md §22): the
    new address and the password; a link goes to the new address, and
    nothing changes until it's opened (confirm_email_change). A ninja's own
    login gets a 404: its address is the guardian's to manage."""
    user = request.user
    if user.is_ninja:
        raise Http404
    form = ChangeEmailForm(user, request.POST if request.method == "POST" else None, request=request)
    if request.method == "POST" and form.is_valid():
        try:
            email_change.request_change(user, form.cleaned_data["new_email"])
        except email_change.EmailChangeError as error:
            form.add_error(None, error.message)
        else:
            messages.success(
                request,
                _(
                    "We sent a link to %(email)s. Open it within %(hours)s hours to confirm; until then your "
                    "address stays %(current)s."
                )
                % {"email": form.cleaned_data["new_email"], "hours": email_change.VALID_HOURS, "current": user.email},
            )
            return redirect("account_home")
    return render(request, "accounts/change_email.html", {"form": form, "valid_hours": email_change.VALID_HOURS})


def confirm_email_change(request, token):
    """The link from the confirmation mail. GET asks, POST changes it (so a
    mail scanner opening the link changes nothing). The family's own link
    needs that account logged in; a link the organisation started works
    logged out too, since the family may not be able to log in any more,
    and then offers a password reset to the new address. Logged in as
    another account: 404."""
    template = "accounts/confirm_email_change.html"
    try:
        change = email_change.read_token(token)
    except email_change.EmailChangeError as error:
        return render(request, template, {"error": error.message}, status=400)
    if request.user.is_authenticated:
        if request.user.pk != change.user.pk:
            raise Http404
    elif change.started_by is None:
        return redirect_to_login(request.get_full_path())

    if request.method != "POST":
        return render(request, template, {"change": change})
    try:
        if request.user.is_authenticated:
            user = email_change.confirm_change(change)
        else:
            # Nobody is logged in: the audit log names the admin who started it.
            with set_actor(change.started_by):
                user = email_change.confirm_change(change)
    except email_change.EmailChangeError as error:
        return render(request, template, {"error": error.message}, status=400)
    if request.user.is_authenticated:
        update_session_auth_hash(request, user)  # the other sessions end, this one stays
        messages.success(request, _("Your email address is now %(email)s.") % {"email": user.email})
        return redirect("account_home")
    return render(request, template, {"done": user})


@login_required
def add_ninja(request):
    """The "Register another child" form on the account page
    (accounts/partials/_add_child.html, AddChildForm) — posts here via htmx
    and swaps in the freshly rendered list, plus the form itself out of
    band: a fresh one after adding, or the posted one with its errors."""
    if request.user.is_ninja:
        raise Http404
    guardian = request.user
    form = AddChildForm(request.POST or None, guardian=guardian)
    if request.method == "POST" and form.is_valid():
        ninja = form.save(commit=False)
        _set_icon(ninja, form.cleaned_data["icon"])
        with transaction.atomic():  # a child never exists without a guardian
            ninja.save()
            Guardianship.objects.create(guardian=guardian, ninja=ninja, **consent_fields(form.cleaned_data["consent"]))
        form = AddChildForm(guardian=guardian)
    return render(
        request,
        "accounts/partials/_children_list.html",
        {
            "guardian": guardian,
            "children": _children_context(guardian),
            "add_child_form": form,
            "add_child_oob": True,
        },
    )


def _badges_queryset(child):
    return child.badges.select_related("badge").order_by("id")


@login_required
def ninja_detail(request, ninja_id):
    child = _get_own_ninja(request, ninja_id, allow_self=True)
    now = timezone.now()
    history = (
        child.registration_set.filter(event__start_time__lt=now)
        .select_related("event", "event__dojo")
        .prefetch_related("event__team__user", "pathways")
        .order_by("-event__start_time")
    )
    upcoming = (
        child.registration_set.filter(event__start_time__gte=now)
        .select_related("event", "event__dojo")
        .order_by("event__start_time")
    )
    belt_history = list(
        child.belts.select_related(
            "belt",
            "awarded_by",
            "awarded_as_membership__user",
            "awarded_as_membership__dojo",
        )
    )

    # Initial batch for the Badges carousel — further batches are
    # lazy-loaded over htmx as it's scrolled, against award_widget below
    # (same approach as the homepage's "Upcoming sessions" carousel).
    badges_page = Paginator(_badges_queryset(child), BADGES_PAGE_SIZE).get_page(1)
    badges_next_page_url = None
    if badges_page.has_next():
        badges_next_page_url = (
            f"{reverse('ninja_badges', kwargs={'ninja_id': child.id})}?page={badges_page.next_page_number()}"
        )

    return render(
        request,
        "accounts/child_detail.html",
        {
            "child": child,
            "history": history,
            "upcoming": upcoming,
            "can_edit": child.guardianships.filter(guardian=request.user).exists(),
            "can_pick_avatar": child.account_id == request.user.pk,
            "badges": badges_page.object_list,
            "badges_next_page_url": badges_next_page_url,
            # Current belt = the highest in the history (newest first).
            "belt_history": belt_history,
            "current_belt": child.current_belt,
            **_login_card_context(child),
        },
    )


def _set_icon(child, icon):
    """Point the child's photo at the picked standard avatar — linked from
    the shared image library (core.image_library), never copied. An
    unknown/empty choice leaves the photo as it was."""
    if icon in dict(TEMPLATE_KID_AVATARS):
        use_library_image(child, "photo", "ninjas", icon)


@login_required
def edit_ninja(request, ninja_id):
    """Click-to-edit for the child detail page's header (see
    partials/_child_header_display.html) — GET swaps the display header
    for a small inline form over htmx; POST saves it and swaps back.
    Guardians only; a ninja's own login can't edit its profile."""
    child = _get_own_ninja(request, ninja_id)
    form = EditChildForm(request.POST or None, instance=child)
    if request.method == "POST" and form.is_valid():
        child = form.save(commit=False)
        home_dojo.set_home_dojo(child, form.cleaned_data["home_dojo"])
        _set_icon(child, form.cleaned_data["icon"])
        child.save()
        return render(
            request,
            "accounts/partials/_child_header_display.html",
            {
                "child": child,
                "can_edit": True,
            },
        )
    return render(request, "accounts/partials/_child_header_edit.html", {"child": child, "form": form})


@login_required
def ninja_avatar(request, ninja_id):
    """A child's own login picks its avatar on its own page, over htmx like
    edit_ninja: GET swaps the header for the picker, POST saves and swaps
    back. Only the standard avatars (ChildAvatarForm); uploading a photo is
    the guardian's. The guardians may use it too, though their edit form
    has the same choice."""
    child = _get_own_ninja(request, ninja_id, allow_self=True)
    form = ChildAvatarForm(child, request.POST or None)
    if request.method == "POST" and form.is_valid():
        _set_icon(child, form.cleaned_data["icon"])
        child.save(update_fields=["photo"])
        return render(
            request,
            "accounts/partials/_child_header_display.html",
            {
                "child": child,
                "can_edit": child.guardianships.filter(guardian=request.user).exists(),
                "can_pick_avatar": child.account_id == request.user.pk,
            },
        )
    return render(request, "accounts/partials/_child_avatar_picker.html", {"child": child, "form": form})


def _login_card_context(child, login_form=None):
    """What the "Own login" card shows besides the child: the form, whether
    two-step login is on, and whether the child still has to use its first
    mail (DATA_MODEL.md §17, §24)."""
    account = child.account
    active = account is not None and account.is_active
    return {
        "login_form": login_form if login_form is not None and login_form.errors else ChildLoginForm(child),
        "login_two_step": active and two_step.is_on(account),
        "login_waiting": active and child_accounts.waiting_for_first_login(account),
    }


def _login_card(request, child, error=None, notice=None, login_form=None):
    """The child page's "Own login" card, after an htmx action on it; a
    plain POST goes back to the page with the message flashed instead.
    `login_form` is the submitted ChildLoginForm, with its errors."""
    if request.headers.get("HX-Request"):
        return render(
            request,
            "accounts/partials/_ninja_login_card.html",
            {
                "child": child,
                "login_error": error,
                "login_notice": notice,
                **_login_card_context(child, login_form),
            },
        )
    if login_form is not None and login_form.errors:
        error = " ".join(login_form.errors["email"])
    if error:
        messages.error(request, error)
    elif notice:
        messages.success(request, notice)
    return redirect("ninja_detail", ninja_id=child.id)


@login_required
def ninja_login_create(request, ninja_id):
    """Give the child their own login (or switch a disabled one back on):
    guardians only, see accounts.child_accounts."""
    child = _get_own_ninja(request, ninja_id)
    if request.method != "POST":
        return redirect("ninja_detail", ninja_id=child.id)
    form = ChildLoginForm(child, request.POST)
    if form.is_valid():
        try:
            account = child_accounts.give_login(
                request.user, child, form.cleaned_data["email"], form.cleaned_data["login_method"]
            )
        except child_accounts.ChildAccountError as error:
            form.add_error("email", str(error))
        else:
            if account.uses_login_link:
                notice = _("Login created: we've mailed %(email)s a link to log in for the first time.")
            else:
                notice = _("Login created: we've mailed %(email)s a link to choose a password.")
            return _login_card(request, child, notice=notice % {"email": account.email})
    return _login_card(request, child, login_form=form)


@login_required
def ninja_login_resend(request, ninja_id):
    child = _get_own_ninja(request, ninja_id)
    if request.method != "POST":
        return redirect("ninja_detail", ninja_id=child.id)
    try:
        child_accounts.resend_login_mail(request.user, child)
    except child_accounts.ChildAccountError as error:
        return _login_card(request, child, error=str(error))
    if child.account.uses_login_link:
        notice = _("We've mailed %(email)s a new link to log in for the first time.")
    else:
        notice = _("We've mailed %(email)s a new link to choose a password.")
    return _login_card(request, child, notice=notice % {"email": child.account.email})


def _guardian_login_action(request, ninja_id, action, template_context, form_class=ConfirmIdentityForm):
    """A guardian's action on their child's login that asks them to confirm
    it's them first (DATA_MODEL.md §24): GET shows the page, a valid POST
    runs `action(form)` and goes back to the child's page with its notice."""
    child = _get_own_ninja(request, ninja_id)
    if not child_accounts.has_active_login(child):
        return redirect("ninja_detail", ninja_id=child.id)
    data = request.POST if request.method == "POST" else None
    if form_class is ChildEmailChangeForm:
        form = form_class(request.user, child.account, data, request=request)
    else:
        form = form_class(request.user, data, request=request)
    if data is not None and form.is_valid():
        try:
            notice = action(child, form)
        except child_accounts.ChildAccountError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, notice)
            return redirect("ninja_detail", ninja_id=child.id)
    return render(request, "accounts/ninja_login_action.html", {"child": child, "form": form, **template_context})


@login_required
def ninja_login_two_step_off(request, ninja_id):
    """The guardian turns off their child's two-step login (a lost phone)."""

    def action(child, form):
        child_accounts.turn_off_two_step(request.user, child)
        return _("Two-step login is off for %(name)s: they log in without the second step now.") % {"name": child.name}

    return _guardian_login_action(request, ninja_id, action, {"kind": "two_step_off"})


@login_required
def ninja_login_use_password(request, ninja_id):
    """The guardian switches their child's login from a login link back to a
    password; the child gets the set-password mail."""

    def action(child, form):
        account = child_accounts.switch_to_password(request.user, child)
        return _("%(name)s now logs in with a password: we've mailed %(email)s a link to choose one.") % {
            "name": child.name,
            "email": account.email,
        }

    return _guardian_login_action(request, ninja_id, action, {"kind": "use_password"})


@login_required
def ninja_login_email(request, ninja_id):
    """The guardian changes the address of their child's login, confirmed
    from the new address (accounts.email_change)."""

    def action(child, form):
        child_accounts.change_email(request.user, child, form.cleaned_data["new_email"])
        return _(
            "We've mailed a link to %(email)s. %(name)s's address changes once it's opened, within %(hours)s hours."
        ) % {"email": form.cleaned_data["new_email"], "name": child.name, "hours": email_change.VALID_HOURS}

    return _guardian_login_action(
        request, ninja_id, action, {"kind": "email", "valid_hours": email_change.VALID_HOURS}, ChildEmailChangeForm
    )


@login_required
def ninja_login_remove(request, ninja_id):
    child = _get_own_ninja(request, ninja_id)
    if request.method != "POST":
        return redirect("ninja_detail", ninja_id=child.id)
    try:
        outcome = child_accounts.remove_login(child)
    except child_accounts.ChildAccountError as error:
        return _login_card(request, child, error=str(error))
    if outcome == child_accounts.DISABLED:
        notice = _(
            "%(name)s's login is switched off. It was on a dojo team, so it's kept for that "
            "team's history; their team places have ended."
        ) % {"name": child.name}
    else:
        notice = _("%(name)s's login is removed.") % {"name": child.name}
    return _login_card(request, child, notice=notice)


@login_required
def ninja_badges(request, ninja_id):
    """Lazy-loaded batches for the child detail page's Badges carousel —
    returns just the next batch of cards (see partials/_badges_page.html),
    triggered by htmx as the carousel is scrolled."""
    child = _get_own_ninja(request, ninja_id, allow_self=True)

    page = Paginator(_badges_queryset(child), BADGES_PAGE_SIZE).get_page(request.GET.get("page"))
    next_page_url = None
    if page.has_next():
        next_page_url = f"{reverse('ninja_badges', kwargs={'ninja_id': child.id})}?page={page.next_page_number()}"

    return render(
        request,
        "accounts/partials/_badges_page.html",
        {
            "badges": page.object_list,
            "badges_next_page_url": next_page_url,
        },
    )


@login_required
def cancel_registration(request, registration_id):
    registration = get_object_or_404(
        Registration.objects.filter(
            Q(ninja__guardianships__guardian=request.user) | Q(ninja__account=request.user)
        ).distinct(),
        id=registration_id,
    )

    if request.method == "POST":
        event = registration.event
        was_confirmed = not registration.waiting_list
        RegistrationCancellation.objects.create(
            ninja=registration.ninja,
            event=event,
            was_waitlisted=registration.waiting_list,
            signed_up_at=registration.created_at,
            cancelled_by=request.user,
        )
        registration.delete()

        if was_confirmed:
            # Cancelling a confirmed spot opens one up — promote whoever's
            # been waiting longest for *this* event (see Registration.position,
            # the FCFS queue events.views.event_signup assigns on signup).
            next_in_line = Registration.objects.filter(event=event, waiting_list=True).order_by("position").first()
            if next_in_line:
                next_in_line.waiting_list = False
                next_in_line.save(update_fields=["waiting_list"])
                waitlist_promoted_mail(next_in_line)
                notify_managers(
                    event.dojo,
                    gettext_lazy("A spot opened up in %(event)s — a waitlisted family is now confirmed."),
                    url=reverse("dojo_dashboard", kwargs={"dojo_id": event.dojo_id}),
                    params={"event": event.name},
                )

    return redirect("account_home")
