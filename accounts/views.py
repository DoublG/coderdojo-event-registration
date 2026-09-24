import re
from pathlib import Path

from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify

from dojos.access import accessible_dojos
from events.models import Registration
from dojos.team import notify_managers

from .forms import (
    ForcedPasswordChangeForm,
    LoginForm,
    RegisterGuardianForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from .models import Guardianship, Participant, User
from .provisioning import unique_username

# Same pool as seed_guardians.py — a guardian adding a child through the
# quick-add widget picks one of these instead of getting a random one.
KID_AVATARS_DIR = Path(__file__).resolve().parent.parent / "dojos" / "seed_data" / "kid_avatars"
KID_AVATAR_FILES = sorted(KID_AVATARS_DIR.glob("*.svg"))

# Small on purpose — small enough that most children's award shelf
# actually spans more than one page, so the lazy-load carousel (same
# pattern as the homepage's "Upcoming sessions", see
# events.views.upcoming_sessions_widget) has something to demonstrate.
AWARDS_PAGE_SIZE = 4

CHILD_NAME_FIELD_RE = re.compile(r"^child_(\d+)_name$")


def _icon_choices():
    choices = []
    for path in KID_AVATAR_FILES:
        category, _, descriptor = path.stem.split("-", 2)
        descriptor = descriptor.replace("-", " ").title()
        label = descriptor if category == "animal" else f"{descriptor} {category.title()}"
        choices.append((path.name, label))
    return choices


def _get_own_ninja(request, ninja_id, allow_self=False):
    """A ninja the logged-in account is a guardian of — or, with
    allow_self, the ninja's own login looking at their own page. 404s
    rather than 403s on a mismatch, so a guessed id doesn't even confirm
    another family's child exists."""
    ninja = get_object_or_404(Participant, id=ninja_id)
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
        ninja = Participant.objects.filter(account=user).first()
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


def _parse_child_rows(post_data):
    """Parses the family-registration form's dynamically-numbered child
    fields (child_<n>_name/dob/level/notes) into a list of row dicts, one
    per index actually present in the POST data. Not a Form/formset: the
    page's "Add another child"/"Remove" buttons (see the template's
    extra_script block) can leave gaps in the numbering (e.g. child_1,
    child_3 after removing child_2), which doesn't map onto Django's
    prefix-fieldname convention — same raw-POST-parsing approach as
    add_child/edit_child above."""
    indices = sorted({int(m.group(1)) for key in post_data if (m := CHILD_NAME_FIELD_RE.match(key))})

    rows = []
    valid_levels = dict(Participant.EXPERIENCE_CHOICES)
    for n in indices:
        name = post_data.get(f"child_{n}_name", "").strip()
        dob_raw = post_data.get(f"child_{n}_dob", "")
        level = post_data.get(f"child_{n}_level", "")
        notes = post_data.get(f"child_{n}_notes", "").strip()

        errors = {}
        if not name:
            errors["name"] = "First name is required."
        date_of_birth = parse_date(dob_raw) if dob_raw else None
        if not date_of_birth:
            errors["dob"] = "Date of birth is required."
        if level not in valid_levels:
            level = ""

        rows.append({
            "index": n, "name": name, "dob": dob_raw, "date_of_birth": date_of_birth,
            "level": level, "notes": notes, "errors": errors,
        })
    return rows


def _create_ninjas(parent, child_rows):
    for row in child_rows:
        ninja = Participant.objects.create(
            name=row["name"], date_of_birth=row["date_of_birth"],
            experience_level=row["level"], allergies_notes=row["notes"],
        )
        Guardianship.objects.create(guardian=parent, ninja=ninja)


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
            children_error = "Add at least one child."

        if form.is_valid() and children_valid:
            first_name, _, last_name = form.cleaned_data["name"].partition(" ")
            parent = User(
                username=unique_username(slugify(form.cleaned_data["name"])),
                email=form.cleaned_data["email"],
                first_name=first_name,
                last_name=last_name,
                phone=form.cleaned_data["phone"],
            )
            parent.set_password(form.cleaned_data["password"])
            parent.save()
            _create_ninjas(parent, child_rows)

            auth_login(request, parent, backend="accounts.backends.EmailOrUsernameBackend")
            return redirect("account_home")
    else:
        form = RegisterGuardianForm()

    return render(request, "accounts/register_guardian.html", {
        "form": form,
        "child_rows": child_rows or [{"index": 1, "name": "", "dob": "", "level": "", "notes": "", "errors": {}}],
        "children_error": children_error,
    })


def _children_context(parent):
    now = timezone.now()
    children = []
    for child in Participant.objects.of_guardian(parent):
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
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            participant = Participant.objects.create(
                name=name, date_of_birth=parse_date(request.POST.get("date_of_birth", "")),
            )
            Guardianship.objects.create(guardian=guardian, ninja=participant)
            icon_path = KID_AVATARS_DIR / request.POST.get("icon", "")
            if icon_path.exists() and icon_path.parent == KID_AVATARS_DIR:
                with open(icon_path, "rb") as f:
                    participant.photo.save(icon_path.name, File(f), save=True)
    children = _children_context(guardian)
    return render(request, "accounts/partials/_children_list.html", {"guardian": guardian, "children": children})


def _awards_queryset(child):
    return child.awards.select_related("award").order_by("id")


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

    # Initial batch for the Awards carousel — further batches are
    # lazy-loaded over htmx as it's scrolled, against award_widget below
    # (same approach as the homepage's "Upcoming sessions" carousel).
    awards_page = Paginator(_awards_queryset(child), AWARDS_PAGE_SIZE).get_page(1)
    awards_next_page_url = None
    if awards_page.has_next():
        awards_next_page_url = (
            f"{reverse('ninja_awards', kwargs={'ninja_id': child.id})}"
            f"?page={awards_page.next_page_number()}"
        )

    return render(request, "accounts/child_detail.html", {
        "child": child, "history": history,
        "can_edit": child.guardianships.filter(guardian=request.user).exists(),
        "awards": awards_page.object_list, "awards_next_page_url": awards_next_page_url,
    })


def _current_icon_value(child):
    """Best-effort match of a child's current photo back to one of the
    dropdown's filenames, so the edit form can preselect it — the saved
    file has a randomised suffix (avatar-01-xyz123.svg), so this matches
    on the stem rather than the exact name."""
    if not child.photo:
        return None
    for path in KID_AVATAR_FILES:
        if path.stem in child.photo.name:
            return path.name
    return None


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
        child.date_of_birth = parse_date(request.POST.get("date_of_birth", ""))

        icon_path = KID_AVATARS_DIR / request.POST.get("icon", "")
        if icon_path.exists() and icon_path.parent == KID_AVATARS_DIR:
            with open(icon_path, "rb") as f:
                child.photo.save(icon_path.name, File(f), save=False)
        child.save()

        return render(request, "accounts/partials/_child_header_display.html", {
            "child": child, "can_edit": True,
        })

    return render(request, "accounts/partials/_child_header_edit.html", {
        "child": child,
        "icon_choices": _icon_choices(), "current_icon": _current_icon_value(child),
    })


@login_required
def ninja_awards(request, ninja_id):
    """Lazy-loaded batches for the child detail page's Awards carousel —
    returns just the next batch of cards (see partials/_awards_page.html),
    triggered by htmx as the carousel is scrolled."""
    child = _get_own_ninja(request, ninja_id, allow_self=True)

    page = Paginator(_awards_queryset(child), AWARDS_PAGE_SIZE).get_page(request.GET.get("page"))
    next_page_url = None
    if page.has_next():
        next_page_url = (
            f"{reverse('ninja_awards', kwargs={'ninja_id': child.id})}"
            f"?page={page.next_page_number()}"
        )

    return render(request, "accounts/partials/_awards_page.html", {
        "awards": page.object_list, "awards_next_page_url": next_page_url,
    })


@login_required
def cancel_registration(request, registration_id):
    registration = get_object_or_404(
        Registration, id=registration_id, participant__guardianships__guardian=request.user,
    )

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
                notify_managers(
                    event.dojo,
                    f"A spot opened up in {event.name} — a waitlisted family is now confirmed.",
                    url=reverse("dojo_dashboard", kwargs={"dojo_id": event.dojo_id}),
                )

    return redirect("account_home")
