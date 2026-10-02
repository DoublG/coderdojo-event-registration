"""Family sign-up: an adult account and its children in one go, self-service."""

from django.contrib.auth import login as auth_login
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.text import slugify

from mailing.categories import MailCategory
from mailing.models import ConsentEvent
from mailing.preferences import set_preference

from .. import login_links
from ..consent import consent_fields
from ..forms import (
    ChildRowsFormSet,
    RegisterGuardianForm,
)
from ..models import Guardianship, User
from ..provisioning import unique_username
from .common import _site_language


def register(request):
    return render(request, "accounts/register.html")


def _create_ninjas(parent, children, consent=False):
    for child_form in children.forms:
        Guardianship.objects.create(guardian=parent, ninja=child_form.save(), **consent_fields(consent))


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
