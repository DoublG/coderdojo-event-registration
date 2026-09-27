"""The organisation dashboard's Sign-in security page (/manage/security/,
shell core/_manage_base.html, DATA_MODEL.md §15): the sign-in policy per role
(accounts.SignInRequirement, applied by accounts.sign_in), how many accounts
in each role already meet it, and turning off someone's two-step login when
they lost their phone and their backup codes. Organisation admin role only
(accounts.organisation.require_organisation_admin)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import sign_in, two_step
from .forms import SignInPolicyForm
from .models import SignInRequirement, User
from .organisation import require_organisation_admin

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
    require_organisation_admin(request)
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
    require_organisation_admin(request)
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
