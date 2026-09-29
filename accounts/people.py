"""The organisation dashboard's People pages (/manage/people/…, shell
core/_manage_base.html, DATA_MODEL.md §23): who holds which organisation
role, giving and taking away roles, open Django admin access, and what each
role opens. The People area only (accounts.organisation.require_area, the
admin role); every change goes through accounts.organisation_people."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import admin_access, organisation_people
from .forms import OrganisationRolesForm
from .models import AdminAccessGrant, User
from .organisation import AREA_LABELS, Area, require_area, role_areas

SEARCH_LIMIT = 25


@login_required
def manage_people(request):
    require_area(request, Area.PEOPLE)
    people = []
    for account in organisation_people.holders():
        held = {row.role for row in account.organisation_roles.all()}
        people.append(
            {
                "account": account,
                "roles": [label for role, label, _description in organisation_people.ROLES if role in held],
                "granted_at": min(row.granted_at for row in account.organisation_roles.all()),
                "needs_sign_in_setup": organisation_people.needs_sign_in_setup(account),
            }
        )
    return render(
        request,
        "accounts/manage/people.html",
        {
            "people": people,
            "open_grants": AdminAccessGrant.objects.open().order_by("expires_at"),
            "superusers": organisation_people.superusers(),
            "active": "people",
        },
    )


@login_required
def manage_people_add(request):
    """Find an existing account to give a role (DATA_MODEL.md §23)."""
    require_area(request, Area.PEOPLE)
    query = request.GET.get("q", "").strip()
    accounts = []
    if query:
        accounts = list(
            User.objects.filter(account_type=User.ADULT, is_active=True)
            .filter(
                Q(email__icontains=query)
                | Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(display_name__icontains=query)
            )
            .prefetch_related("organisation_roles")
            .order_by("last_name", "first_name", "username")[:SEARCH_LIMIT]
        )
    return render(
        request,
        "accounts/manage/people_add.html",
        {"query": query, "accounts": accounts, "search_limit": SEARCH_LIMIT, "active": "people"},
    )


@login_required
def manage_person(request, user_id):
    """One person's organisation roles, their history and their Django admin
    access."""
    require_area(request, Area.PEOPLE)
    account = get_object_or_404(User, pk=user_id, account_type=User.ADULT)
    is_self = account.pk == request.user.pk
    # Bound on any POST: with every box unticked the POST is empty but still a save.
    form = OrganisationRolesForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            added, removed = organisation_people.set_roles(account, form.cleaned_data["roles"], by=request.user)
        except organisation_people.OrganisationPeopleError as error:
            messages.error(request, str(error))
        else:
            if added or removed:
                messages.success(request, _("Roles saved. %(name)s gets a mail.") % {"name": account.team_name})
        return redirect("manage_person", user_id=account.pk)
    held = organisation_people.roles_of(account)
    return render(
        request,
        "accounts/manage/person.html",
        {
            "account": account,
            "is_self": is_self,
            "roles": [
                (role, label, description, role in held) for role, label, description in organisation_people.ROLES
            ],
            "history": organisation_people.role_history(account),
            "grants": account.admin_access_grants.all()[:20],
            "open_grant": admin_access.open_grant(account),
            "needs_sign_in_setup": held and organisation_people.needs_sign_in_setup(account),
            "active": "people",
        },
    )


@login_required
def manage_people_roles(request):
    """What each role opens, read-only (the roles are fixed in code)."""
    require_area(request, Area.PEOPLE)
    roles = organisation_people.ROLES
    opened = {role: set(role_areas(role)) for role, _label, _description in roles}
    rows = [(label, [area in opened[role] for role, _l, _d in roles]) for area, label in AREA_LABELS.items()]
    return render(
        request,
        "accounts/manage/people_roles.html",
        {
            "roles": roles,
            "rows": rows,
            "hours": admin_access.ADMIN_ACCESS_HOURS,
            "active": "people",
        },
    )


@login_required
@require_POST
def manage_people_end_access(request, grant_id):
    """End someone's open Django admin access now."""
    require_area(request, Area.PEOPLE)
    grant = get_object_or_404(AdminAccessGrant, pk=grant_id)
    try:
        organisation_people.end_access(grant, by=request.user)
    except organisation_people.OrganisationPeopleError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request, _("%(name)s's access to the Django admin has ended.") % {"name": grant.account.team_name}
        )
    back = request.POST.get("next")
    if back == "person":
        return redirect("manage_person", user_id=grant.account_id)
    return redirect("manage_people")
