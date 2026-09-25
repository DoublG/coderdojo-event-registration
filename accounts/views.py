import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.utils.translation import gettext as _

from core.image_library import library_filename, use_library_image
from dojos.access import accessible_dojos
from dojos.team import notify_managers
from events.models import Registration, RegistrationCancellation
from mailing.automated import waitlist_promoted_mail
from mailing.categories import MailCategory
from mailing.models import ConsentEvent
from mailing.preferences import set_preference

from . import child_accounts, home_dojo
from .forms import (
    ForcedPasswordChangeForm,
    LoginForm,
    RegisterGuardianForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from .models import Guardianship, Ninja, User, ninja_birth_date_error
from .provisioning import unique_username
from .template_avatars import TEMPLATE_KID_AVATARS

# Small on purpose — small enough that most children's award shelf
# actually spans more than one page, so the lazy-load carousel (same
# pattern as the homepage's "Upcoming sessions", see
# events.views.upcoming_sessions_widget) has something to demonstrate.
BADGES_PAGE_SIZE = 4

CHILD_NAME_FIELD_RE = re.compile(r"^child_(\d+)_name$")


def _icon_choices():
    # Same set as seed_guardians.py — a guardian adding a child through the
    # quick-add widget picks one of these instead of getting a random one.
    return TEMPLATE_KID_AVATARS


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

    # Owners and helpers land on the admin area of the first dojo they can
    # open — see dojos.access for who counts.
    admin_dojo = accessible_dojos(user).first()
    if admin_dojo is not None:
        return reverse("dojo_dashboard", kwargs={"dojo_id": admin_dojo.id})

    if user.is_ninja:
        ninja = Ninja.objects.filter(account=user).first()
        return reverse("ninja_detail", kwargs={"ninja_id": ninja.id}) if ninja else reverse("home")

    return reverse("account_home")


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
            # A lapsed background check never blocks login — it only removes
            # dojo-team access (dojos.access); see the account page.
            if user is not None:
                auth_login(request, user)
                return redirect(_post_login_redirect(request, user))
            else:
                error = _("That email/password combination doesn't match an account.")
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


def _parse_child_rows(post_data):
    """Parses the family-registration form's dynamically-numbered child
    fields (child_<n>_name/dob/notes) into a list of row dicts, one
    per index actually present in the POST data. Not a Form/formset: the
    page's "Add another child"/"Remove" buttons (see the template's
    extra_script block) can leave gaps in the numbering (e.g. child_1,
    child_3 after removing child_2), which doesn't map onto Django's
    prefix-fieldname convention — same raw-POST-parsing approach as
    add_child/edit_child above."""
    indices = sorted({int(m.group(1)) for key in post_data if (m := CHILD_NAME_FIELD_RE.match(key))})

    rows = []
    for n in indices:
        name = post_data.get(f"child_{n}_name", "").strip()
        dob_raw = post_data.get(f"child_{n}_dob", "")
        notes = post_data.get(f"child_{n}_notes", "").strip()
        gender = _clean_gender(post_data.get(f"child_{n}_gender"))

        errors = {}
        if not name:
            errors["name"] = _("First name is required.")
        date_of_birth = parse_date(dob_raw) if dob_raw else None
        if not date_of_birth:
            errors["dob"] = _("Date of birth is required.")
        elif dob_error := ninja_birth_date_error(date_of_birth):
            errors["dob"] = dob_error

        rows.append({
            "index": n, "name": name, "dob": dob_raw, "date_of_birth": date_of_birth,
            "notes": notes, "gender": gender, "errors": errors,
        })
    return rows


def _clean_gender(value):
    """A posted gender, or "Prefer not to say" for anything else (including
    a form that didn't send one). Optional everywhere, never an error."""
    return value if value in dict(Ninja.GENDER_CHOICES) else Ninja.UNSPECIFIED


def _create_ninjas(parent, child_rows):
    for row in child_rows:
        ninja = Ninja.objects.create(
            name=row["name"], date_of_birth=row["date_of_birth"], allergies_notes=row["notes"], gender=row["gender"],
        )
        Guardianship.objects.create(guardian=parent, ninja=ninja)


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

    child_rows = None
    children_error = None

    if request.method == "POST":
        form = RegisterGuardianForm(request.POST)
        child_rows = _parse_child_rows(request.POST)
        children_valid = bool(child_rows) and not any(row["errors"] for row in child_rows)
        if not child_rows:
            children_error = _("Add at least one child.")

        if form.is_valid() and children_valid:
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
            parent.set_password(form.cleaned_data["password"])
            parent.save()
            _create_ninjas(parent, child_rows)
            if form.cleaned_data["newsletter"]:
                set_preference(parent, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)

            auth_login(request, parent, backend="accounts.backends.EmailOrUsernameBackend")
            return redirect("account_home")
    else:
        form = RegisterGuardianForm(initial={"preferred_language": _site_language(request)})

    return render(request, "accounts/register_guardian.html", {
        "form": form,
        "child_rows": child_rows or [{"index": 1, "name": "", "dob": "", "notes": "", "gender": Ninja.UNSPECIFIED, "errors": {}}],
        "children_error": children_error,
        "gender_choices": Ninja.GENDER_CHOICES,
    })


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
    children = _children_context(request.user)
    applications = list(request.user.applications.all())
    active_kinds = {a.kind for a in applications if a.status != "rejected"}
    return render(request, "accounts/guardian_detail.html", {
        "guardian": request.user, "children": children, "icon_choices": _icon_choices(),
        "gender_choices": Ninja.GENDER_CHOICES,
        "applications": applications,
        "has_champion_application": "champion" in active_kinds,
        "has_mentor_application": "mentor" in active_kinds,
    })


@login_required
def add_ninja(request):
    """The "+ Add a child" widget on the account page (see
    accounts/partials/_children_list.html) — posts here via htmx and
    swaps in the freshly rendered list, so the page updates without a
    full reload."""
    if request.user.is_ninja:
        raise Http404
    guardian = request.user
    add_error = None
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        date_of_birth = parse_date(request.POST.get("date_of_birth", ""))
        add_error = ninja_birth_date_error(date_of_birth)
        if name and not add_error:
            ninja = Ninja(name=name, date_of_birth=date_of_birth, gender=_clean_gender(request.POST.get("gender")))
            _set_icon(ninja, request.POST.get("icon", ""))
            ninja.save()
            Guardianship.objects.create(guardian=guardian, ninja=ninja)
    children = _children_context(guardian)
    return render(request, "accounts/partials/_children_list.html", {
        "guardian": guardian, "children": children, "add_error": add_error,
    })


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
    belt_history = list(child.belts.select_related(
        "belt", "awarded_by", "awarded_as_membership__user", "awarded_as_membership__dojo",
    ))

    # Initial batch for the Badges carousel — further batches are
    # lazy-loaded over htmx as it's scrolled, against award_widget below
    # (same approach as the homepage's "Upcoming sessions" carousel).
    badges_page = Paginator(_badges_queryset(child), BADGES_PAGE_SIZE).get_page(1)
    badges_next_page_url = None
    if badges_page.has_next():
        badges_next_page_url = (
            f"{reverse('ninja_badges', kwargs={'ninja_id': child.id})}"
            f"?page={badges_page.next_page_number()}"
        )

    return render(request, "accounts/child_detail.html", {
        "child": child, "history": history, "upcoming": upcoming,
        "can_edit": child.guardianships.filter(guardian=request.user).exists(),
        "badges": badges_page.object_list, "badges_next_page_url": badges_next_page_url,
        # Current belt = the highest in the history (newest first).
        "belt_history": belt_history, "current_belt": child.current_belt,
    })


def _set_icon(child, icon):
    """Point the child's photo at the picked standard avatar — linked from
    the shared image library (core.image_library), never copied. An
    unknown/empty choice leaves the photo as it was."""
    if icon in dict(TEMPLATE_KID_AVATARS):
        use_library_image(child, "photo", "ninjas", icon)


def _edit_context(child, **extra):
    return {
        "child": child, "gender_choices": Ninja.GENDER_CHOICES,
        "icon_choices": _icon_choices(), "current_icon": _current_icon_value(child),
        "home_dojo_choices": home_dojo.home_dojo_choices(), **extra,
    }


def _current_icon_value(child):
    """The dropdown's filename for the child's current photo, so the edit
    form can preselect it (None for an uploaded photo or none at all)."""
    return library_filename(child.photo, "ninjas")


@login_required
def edit_ninja(request, ninja_id):
    """Click-to-edit for the child detail page's header (see
    partials/_child_header_display.html) — GET swaps the display header
    for a small inline form over htmx; POST saves it and swaps back.
    Guardians only; a ninja's own login can't edit its profile."""
    child = _get_own_ninja(request, ninja_id)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            child.name = name
        date_of_birth = parse_date(request.POST.get("date_of_birth", ""))
        if date_of_birth != child.date_of_birth and (dob_error := ninja_birth_date_error(date_of_birth)):
            return render(request, "accounts/partials/_child_header_edit.html", _edit_context(child, dob_error=dob_error))
        child.date_of_birth = date_of_birth
        if "gender" in request.POST:
            child.gender = _clean_gender(request.POST["gender"])
        # Like gender: a form without the field keeps what's stored, and an
        # unknown id (not a public dojo) changes nothing.
        if "home_dojo" in request.POST:
            dojo_id = request.POST["home_dojo"]
            if not dojo_id:
                home_dojo.set_home_dojo(child, None)
            elif dojo := home_dojo.home_dojo_choices().filter(pk=dojo_id).first():
                home_dojo.set_home_dojo(child, dojo)

        _set_icon(child, request.POST.get("icon", ""))
        child.save()

        return render(request, "accounts/partials/_child_header_display.html", {
            "child": child, "can_edit": True,
        })

    return render(request, "accounts/partials/_child_header_edit.html", _edit_context(child))


def _login_card(request, child, error=None, notice=None):
    """The child page's "Own login" card, after an htmx action on it; a
    plain POST goes back to the page with the message flashed instead."""
    if request.headers.get("HX-Request"):
        return render(request, "accounts/partials/_ninja_login_card.html", {
            "child": child, "login_error": error, "login_notice": notice,
            "posted_email": request.POST.get("email", "") if error else "",
        })
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
    try:
        account = child_accounts.give_login(request.user, child, request.POST.get("email"))
    except child_accounts.ChildAccountError as error:
        return _login_card(request, child, error=str(error))
    return _login_card(request, child, notice=_("Login created: we've mailed %(email)s a link to choose a password.") % {
        "email": account.email,
    })


@login_required
def ninja_login_resend(request, ninja_id):
    child = _get_own_ninja(request, ninja_id)
    if request.method != "POST":
        return redirect("ninja_detail", ninja_id=child.id)
    try:
        child_accounts.resend_login_mail(request.user, child)
    except child_accounts.ChildAccountError as error:
        return _login_card(request, child, error=str(error))
    return _login_card(request, child, notice=_("We've mailed %(email)s a new link to choose a password.") % {
        "email": child.account.email,
    })


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
        notice = _("%(name)s's login is switched off. It was on a dojo team, so it's kept for that "
                   "team's history; their team places have ended.") % {"name": child.name}
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
        next_page_url = (
            f"{reverse('ninja_badges', kwargs={'ninja_id': child.id})}"
            f"?page={page.next_page_number()}"
        )

    return render(request, "accounts/partials/_badges_page.html", {
        "badges": page.object_list, "badges_next_page_url": next_page_url,
    })


@login_required
def cancel_registration(request, registration_id):
    registration = get_object_or_404(
        Registration.objects.filter(Q(ninja__guardianships__guardian=request.user) | Q(ninja__account=request.user))
        .distinct(),
        id=registration_id,
    )

    if request.method == "POST":
        event = registration.event
        was_confirmed = not registration.waiting_list
        RegistrationCancellation.objects.create(
            ninja=registration.ninja, event=event, was_waitlisted=registration.waiting_list,
            signed_up_at=registration.created_at, cancelled_by=request.user,
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
                    f"A spot opened up in {event.name} — a waitlisted family is now confirmed.",
                    url=reverse("dojo_dashboard", kwargs={"dojo_id": event.dojo_id}),
                )

    return redirect("account_home")
