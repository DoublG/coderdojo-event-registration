"""The organisation dashboard's Sign-in security page (/manage/security/,
shell core/_manage_base.html, DATA_MODEL.md §15): the sign-in policy per role
(accounts.SignInRequirement, applied by accounts.sign_in), how many accounts
in each role already meet it, and turning off someone's two-step login when
they lost their phone and their backup codes. The Security area only
(accounts.organisation.require_area, the admin role, DATA_MODEL.md §23)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.manage_nav import require_organisation_context

from . import admin_access, sign_in, two_step
from .forms import AdminAccessForm, SignInPolicyForm
from .models import SignInRequirement, User
from .organisation import Area, require_area

SEARCH_LIMIT = 25


def _role_counts():
    counts = {}
    for role, _label in SignInRequirement.ROLE_CHOICES:
        accounts = sign_in.accounts_with_role(role)
        on, passkey = sign_in.with_two_step(accounts)
        counts[role] = {"total": accounts.count(), "on": on.count(), "passkey": passkey.count()}
    return counts


@login_required
def security_policy(request):
    require_area(request, Area.SECURITY)
    requirements = {row.role: row for row in SignInRequirement.objects.all()}
    form = SignInPolicyForm(request.POST or None, requirements=requirements)
    if request.method == "POST" and form.is_valid():
        if form.save(updated_by=request.user):
            messages.success(request, _("Sign-in policy saved."))
        return redirect("manage_security")

    query = request.GET.get("q", "").strip()
    accounts = []
    if query:
        accounts = list(
            User.objects.filter(account_type=User.ADULT)
            .filter(
                Q(email__icontains=query)
                | Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            )
            .order_by("last_name", "first_name", "username")[:SEARCH_LIMIT]
        )
        for account in accounts:
            account.two_step_methods = two_step.methods(account)
    counts = _role_counts()
    return render(
        request,
        "accounts/manage/security.html",
        {
            "form": form,
            "rows": [(*row, counts[row[0]]) for row in form.rows()],
            "query": query,
            "accounts": accounts,
            "search_limit": SEARCH_LIMIT,
            "active": "security",
        },
    )


@login_required
@require_POST
def turn_off_two_step(request, user_id):
    """For someone who lost every way to confirm it's them: removes their
    apps, passkeys and backup codes, and mails them. If their role needs
    two-step login, they set it up again at their next login."""
    require_area(request, Area.SECURITY)
    account = get_object_or_404(User, pk=user_id, account_type=User.ADULT)
    back = reverse("manage_security")
    if request.POST.get("q"):
        back += "?" + urlencode({"q": request.POST["q"]})
    if account == request.user:
        messages.error(request, _("Change your own sign-in methods on your account's Sign-in security page."))
        return redirect(back)
    two_step.turn_off(account, by_organisation=True)
    messages.success(
        request, _("Two-step login is off for %(name)s.") % {"name": account.get_full_name() or account.username}
    )
    return redirect(back)


def _require_may_ask(request):
    """The Django admin access page: any organisation role (a 404 otherwise,
    also for a superuser without one: theirs is never time-boxed)."""
    from django.http import Http404

    require_organisation_context(request)
    if not admin_access.may_ask(request.user):
        raise Http404


@login_required
def manage_admin_access(request):
    """Ask for the Django admin for 12 hours, see when it ends, and your
    earlier grants (DATA_MODEL.md §23)."""
    _require_may_ask(request)
    grant = admin_access.open_grant(request.user)
    form = AdminAccessForm(request.user, request.POST if request.method == "POST" else None, request=request)
    if request.method == "POST" and grant is None and form.is_valid():
        try:
            grant = admin_access.request_access(request.user, form.cleaned_data["reason"])
        except admin_access.AdminAccessError as error:
            form.add_error(None, str(error))
        else:
            messages.success(
                request,
                _("You have access to the Django admin until %(until)s.") % {"until": admin_access.until_label(grant)},
            )
            return redirect("manage_admin_access")
    return render(
        request,
        "accounts/manage/admin_access.html",
        {
            "form": form,
            "grant": grant,
            "until": admin_access.until_label(grant) if grant else "",
            "hours": admin_access.ADMIN_ACCESS_HOURS,
            "history": request.user.admin_access_grants.all()[:20],
            "active": "admin_access",
        },
    )


@login_required
@require_POST
def manage_admin_access_end(request):
    """End your own access now."""
    _require_may_ask(request)
    if admin_access.end_for(request.user, by=request.user):
        messages.success(request, _("Your access to the Django admin has ended."))
    return redirect("manage_admin_access")
