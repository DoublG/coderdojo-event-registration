"""Getting a copy of your data (DATA_MODEL.md §16 phase 3, `privacy.export`)
and deleting an account (phase 5, `privacy.deletion`): the family's
"Download my data" and "Delete my account", and the organisation
dashboard's Privacy page (/manage/privacy/, shell core/_manage_base.html),
for requests that come in by mail or post."""

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from accounts.models import User
from accounts.organisation import require_organisation_admin
from core.audit import log_access

from .deletion import delete_account, preview
from .export import export_filename, export_json
from .retention import champions_needing_attention

# One download per account per minute: an export runs a query per model.
EXPORT_INTERVAL_SECONDS = 60
SEARCH_LIMIT = 25


def _download(user):
    response = HttpResponse(export_json(user), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{export_filename(user)}"'
    return response


@login_required
def download_my_data(request):
    """The account's own data and its children's, as a JSON file. A ninja's
    own login gets only its own."""
    # cache.add is False when the key exists; None when the cache is down
    # (IGNORE_EXCEPTIONS), and then the download goes ahead.
    if cache.add(f"privacy:export:{request.user.pk}", 1, EXPORT_INTERVAL_SECONDS) is False:
        messages.error(request, _("You just downloaded your data. Please wait a minute before trying again."))
        return redirect("account_home")
    return _download(request.user)


@login_required
def manage_privacy(request):
    """Find an account to answer a request for a copy of someone's data,
    and the champions the retention job is waiting on."""
    require_organisation_admin(request)
    query = request.GET.get("q", "").strip()
    accounts = []
    if query:
        accounts = (
            User.objects.filter(
                Q(email__icontains=query)
                | Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(guardianships__ninja__name__icontains=query)
            )
            .annotate(children_count=Count("guardianships", distinct=True))
            .distinct()
            .order_by("last_name", "first_name", "username")[:SEARCH_LIMIT]
        )
    return render(
        request,
        "privacy/manage/privacy.html",
        {
            "query": query,
            "accounts": accounts,
            "search_limit": SEARCH_LIMIT,
            "attention": champions_needing_attention(),
            "active": "privacy",
        },
    )


@login_required
def manage_privacy_export(request, user_id):
    require_organisation_admin(request)
    user = get_object_or_404(User, pk=user_id)
    log_access(user)  # who handed out whose data: recorded in the audit log
    return _download(user)


@login_required
def delete_my_account(request):
    """The family deletes its own account: what goes and what stays first,
    then the password to confirm. Not for a child's own login: that's the
    guardian's to take away."""
    user = request.user
    if user.is_ninja:
        raise Http404
    result = preview(user)
    error = None
    if request.method == "POST" and result.possible:
        if not user.check_password(request.POST.get("password", "")):
            error = _("That isn't your password.")
        else:
            delete_account(user)
            logout(request)
            return render(request, "privacy/account_deleted.html")
    return render(request, "privacy/delete_account.html", {"preview": result, "error": error})


@login_required
def manage_privacy_delete(request, user_id):
    """The organisation deletes an account on a request by mail or post:
    the same preview, confirmed by typing the account's username."""
    require_organisation_admin(request)
    account = get_object_or_404(User, pk=user_id)
    result = preview(account)
    error = None
    if request.method == "POST" and result.possible:
        if request.POST.get("confirm", "").strip() != account.get_username():
            error = _("Type the account's username to confirm.")
        else:
            delete_account(account, requested_by=request.user)
            messages.success(request, _("The account has been deleted."))
            return redirect("manage_privacy")
    return render(
        request,
        "privacy/manage/delete.html",
        {"account": account, "preview": result, "error": error, "active": "privacy"},
    )
