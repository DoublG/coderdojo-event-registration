"""Family sign-up: an adult account and its children in one go, self-service.
Also register_individual: the same self-service sign-up for an adult with no
children, who still wants an account to apply to start a dojo or volunteer."""

from django.contrib.auth import login as auth_login
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify

from mailing.categories import MailCategory
from mailing.models import ConsentEvent
from mailing.preferences import set_preference

from .. import login_links
from ..consent import consent_fields
from ..forms import (
    ChildRowsFormSet,
    RegisterGuardianForm,
    RegisterIndividualForm,
)
from ..models import Guardianship, User
from ..provisioning import unique_username
from .auth import _post_login_redirect
from .common import _site_language


def register(request):
    return render(request, "accounts/register.html")


def _signup_next(request):
    """The page to return to once the account is made: wherever sent the
    visitor to sign up first — an event's sign-up page (event_signup.html's
    login wall), register_dojo or register_helper (the register.html
    chooser's cards link through with ?next=). Never an open redirect."""
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    return next_url if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}) else ""


def _create_ninjas(parent, children, consent=False):
    for child_form in children.forms:
        Guardianship.objects.create(guardian=parent, ninja=child_form.save(), **consent_fields(consent))


def register_guardian(request):
    """Family sign-up for someone without an account. Already logged in?
    Any adult account can add its children from the account page, so
    there's nothing to register."""
    if request.user.is_authenticated:
        return redirect("account_home")

    next_url = _signup_next(request)
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
                # login, and proves the address (DATA_MODEL.md §24). It
                # carries `next` along so it still lands where they meant to go.
                login_links.send_login_link(parent, next_url=next_url or None, first=True)
                return render(
                    request,
                    "accounts/register_check_inbox.html",
                    {"email": parent.email, "valid_days": login_links.FIRST_LINK_VALID_DAYS},
                )
            auth_login(request, parent, backend="accounts.backends.EmailOrUsernameBackend")
            return redirect(next_url or _post_login_redirect(request, parent))
    else:
        form = RegisterGuardianForm(initial={"preferred_language": _site_language(request)})
        children = ChildRowsFormSet()

    return render(request, "accounts/register_guardian.html", {"form": form, "children": children, "next": next_url})


def register_individual(request):
    """Self-service sign-up for an adult with no children of their own
    (accounts/register.html's "Start a new dojo" / "Become a mentor or
    volunteer" cards, for a visitor who isn't logged in yet): the same
    account-level details as family sign-up, minus the children. Already
    logged in? Nothing to register — there's one account per person."""
    if request.user.is_authenticated:
        return redirect("account_home")

    next_url = _signup_next(request)
    if request.method == "POST":
        form = RegisterIndividualForm(request.POST)
        if form.is_valid():
            first_name, _sep, last_name = form.cleaned_data["name"].partition(" ")
            account = User(
                username=unique_username(slugify(form.cleaned_data["name"])),
                email=form.cleaned_data["email"],
                first_name=first_name,
                last_name=last_name,
                phone=form.cleaned_data["phone"],
                postal_code=form.cleaned_data["postal_code"],
                preferred_language=form.cleaned_data["preferred_language"] or _site_language(request),
            )
            if form.uses_link:
                account.login_method = User.LOGIN_LINK
                account.set_unusable_password()
            else:
                account.set_password(form.cleaned_data["password"])
            with transaction.atomic():
                account.save()
                if form.cleaned_data["newsletter"]:
                    set_preference(account, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)

            if form.uses_link:
                # Not logged in yet: opening the first link is the first
                # login, and proves the address (DATA_MODEL.md §24). It
                # carries `next` along so it still lands on the application.
                login_links.send_login_link(account, next_url=next_url or None, first=True)
                return render(
                    request,
                    "accounts/register_check_inbox.html",
                    {"email": account.email, "valid_days": login_links.FIRST_LINK_VALID_DAYS},
                )
            auth_login(request, account, backend="accounts.backends.EmailOrUsernameBackend")
            return redirect(next_url or _post_login_redirect(request, account))
    else:
        form = RegisterIndividualForm(initial={"preferred_language": _site_language(request)})

    return render(request, "accounts/register_individual.html", {"form": form, "next": next_url})
