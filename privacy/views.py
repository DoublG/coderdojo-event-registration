"""Getting a copy of your data (DATA_MODEL.md §16 phase 3, `privacy.export`)
and deleting an account (phase 5, `privacy.deletion`): the family's
"Download my data" and "Delete my account", and the organisation
dashboard's Privacy page (/manage/privacy/, shell core/_manage_base.html),
for requests that come in by mail or post; there the organisation can also
start an email change (accounts.email_change, DATA_MODEL.md §22)."""

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from accounts import email_change
from accounts.forms import ConfirmIdentityForm, OrganisationEmailChangeForm
from accounts.models import Ninja, User
from accounts.organisation import Area, require_area
from core.audit import log_access

from . import merge
from .deletion import delete_account, preview
from .export import export_filename, export_json
from .forms import ConfirmUsernameForm
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
    require_area(request, Area.PRIVACY)
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
                | Q(guardianships__ninja__family_name__icontains=query)
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
    require_area(request, Area.PRIVACY)
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
    form = ConfirmIdentityForm(
        user, request.POST if request.method == "POST" else None, request=request, label=_("Your password, to confirm")
    )
    if request.method == "POST" and result.possible and form.is_valid():
        delete_account(user)
        logout(request)
        return render(request, "privacy/account_deleted.html")
    return render(request, "privacy/delete_account.html", {"preview": result, "form": form})


@login_required
def manage_privacy_delete(request, user_id):
    """The organisation deletes an account on a request by mail or post:
    the same preview, confirmed by typing the account's username."""
    require_area(request, Area.PRIVACY)
    account = get_object_or_404(User, pk=user_id)
    result = preview(account)
    form = ConfirmUsernameForm(account, request.POST or None)
    if request.method == "POST" and result.possible and form.is_valid():
        delete_account(account, requested_by=request.user)
        messages.success(request, _("The account has been deleted."))
        return redirect("manage_privacy")
    return render(
        request,
        "privacy/manage/delete.html",
        {"account": account, "preview": result, "form": form, "active": "privacy"},
    )


@login_required
def manage_privacy_email(request, user_id):
    """The organisation starts an email change for a family that lost its
    old mailbox (DATA_MODEL.md §22): a link goes to the new address, which
    they confirm without logging in. Not for ninja logins, superusers or
    organisation roles (accounts.email_change.organisation_blocker)."""
    require_area(request, Area.PRIVACY)
    account = get_object_or_404(User, pk=user_id)
    blocker = email_change.organisation_blocker(account)
    form = OrganisationEmailChangeForm(account, request.POST or None)
    if request.method == "POST" and not blocker and form.is_valid():
        try:
            email_change.request_change(account, form.cleaned_data["new_email"], started_by=request.user)
        except email_change.EmailChangeError as error:
            form.add_error(None, error.message)
        else:
            messages.success(
                request,
                _(
                    "A confirmation link was sent to %(email)s. The address changes once they open it (within "
                    "%(hours)s hours)."
                )
                % {"email": form.cleaned_data["new_email"], "hours": email_change.VALID_HOURS},
            )
            return redirect("manage_privacy")
    return render(
        request,
        "privacy/manage/email.html",
        {"account": account, "blocker": blocker, "form": form, "active": "privacy"},
    )


def _merge_rows(pairs):
    """The pairs with what each card holds, so the organisation sees which
    one to keep: places booked, badges, belts and the guardians."""
    ids = {n.pk for pair in pairs for n in (pair.first, pair.second)}
    cards = {
        n.pk: n
        for n in Ninja.objects.filter(pk__in=ids)
        .annotate(
            registration_total=Count("registration", distinct=True),
            badge_total=Count("badges", distinct=True),
            belt_total=Count("belts", distinct=True),
        )
        .select_related("home_dojo")
        .prefetch_related("guardianships__guardian")
    }
    rows = []
    for pair in pairs:
        first, second = cards[pair.first.pk], cards[pair.second.pk]
        # The card with more history is the one to keep, the older one on a tie.
        keep_first = (first.registration_total + first.badge_total + first.belt_total) >= (
            second.registration_total + second.badge_total + second.belt_total
        )
        rows.append({"cards": [first, second], "keep": first if keep_first else second})
    return rows


@login_required
def manage_privacy_merge(request):
    """Children signed up twice by the same family (the same name and a
    guardian in common): merge the duplicate card into the one that stays
    (privacy.merge). Irreversible, so the button asks first."""
    require_area(request, Area.PRIVACY)
    if request.method == "POST":
        keep = Ninja.objects.filter(pk=request.POST.get("keep", "").strip() or 0).first()
        duplicate = Ninja.objects.filter(pk=request.POST.get("duplicate", "").strip() or 0).first()
        if keep is None or duplicate is None:
            messages.error(request, _("One of the two children doesn't exist any more."))
        else:
            try:
                merge.merge_children(keep, duplicate)
            except merge.MergeError as problem:
                messages.error(request, str(problem))
            else:
                messages.success(
                    request,
                    _("%(duplicate)s was merged into %(keep)s.")
                    % {"duplicate": duplicate.full_name, "keep": keep.full_name},
                )
        return redirect("manage_privacy_merge")
    return render(
        request,
        "privacy/manage/merge.html",
        {"rows": _merge_rows(merge.candidates()), "active": "privacy"},
    )
