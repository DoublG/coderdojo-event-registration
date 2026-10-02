"""A child's own login, the guardian's to give and take away
(accounts.child_accounts): the Own login card and each action on it, confirmed
with the guardian's own identity."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from .. import child_accounts, email_change, two_step
from ..forms import (
    ChildEmailChangeForm,
    ChildLoginForm,
    ConfirmIdentityForm,
)
from .common import _get_own_ninja


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
