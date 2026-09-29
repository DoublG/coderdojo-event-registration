"""The organisation dashboard's People pages (/manage/people/…, shell
core/_manage_base.html, DATA_MODEL.md §23): who holds which organisation
role, giving and taking away roles, invitations for people without an
account, open Django admin access, and what each role opens. The People
area only (accounts.organisation.require_area, the admin role); every change
goes through accounts.organisation_people and accounts.invitations.

Also the invitation's own public pages (/invitation/<token>/…): accepting
it, and creating an account from it."""

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import admin_access, invitations, organisation_people
from .forms import InvitationForm, InvitedSignUpForm, OrganisationRolesForm
from .models import AdminAccessGrant, OrganisationInvitation, User
from .organisation import AREA_LABELS, Area, require_area, role_areas
from .views import _site_language

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
            "invitations": [
                (invitation, [organisation_people.ROLE_LABELS.get(role, role) for role in invitation.roles])
                for invitation in OrganisationInvitation.objects.pending()
            ],
            "superusers": organisation_people.superusers(),
            "active": "people",
        },
    )


@login_required
def manage_people_add(request):
    """Find an existing account to give a role, or invite someone without
    one (DATA_MODEL.md §23)."""
    require_area(request, Area.PEOPLE)
    invite_form = InvitationForm(request.POST or None, initial={"language": _site_language(request)})
    if request.method == "POST" and invite_form.is_valid():
        data = invite_form.cleaned_data
        try:
            invitations.invite(data["email"], data["name"], data["roles"], by=request.user, language=data["language"])
        except invitations.InvitationError as error:
            invite_form.add_error(None, str(error))
        else:
            messages.success(request, _("Invitation sent to %(email)s.") % {"email": data["email"]})
            return redirect("manage_people")
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
        {
            "query": query,
            "accounts": accounts,
            "search_limit": SEARCH_LIMIT,
            "invite_form": invite_form,
            "role_descriptions": organisation_people.ROLES,
            "active": "people",
        },
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


@login_required
@require_POST
def manage_invitation_resend(request, invitation_id):
    require_area(request, Area.PEOPLE)
    invitation = get_object_or_404(OrganisationInvitation, pk=invitation_id)
    try:
        invitations.resend(invitation, by=request.user)
    except invitations.InvitationError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("Invitation sent again to %(email)s.") % {"email": invitation.email})
    return redirect("manage_people")


@login_required
@require_POST
def manage_invitation_withdraw(request, invitation_id):
    require_area(request, Area.PEOPLE)
    invitation = get_object_or_404(OrganisationInvitation, pk=invitation_id)
    try:
        invitations.withdraw(invitation)
    except invitations.InvitationError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("Invitation to %(email)s withdrawn.") % {"email": invitation.email})
    return redirect("manage_people")


def organisation_invitation(request, token):
    """The link in the invitation mail: who invited you to which roles, then
    create an account, log in, or (logged in with the invited address)
    accept. GET shows, POST accepts, so a mail scanner can't accept it."""
    invitation = invitations.find(token)
    state = "invalid"
    if invitation is not None and invitation.is_pending:
        if request.user.is_authenticated:
            state = "accept" if invitations.can_accept(invitation, request.user) else "other_account"
        elif User.objects.filter(email__iexact=invitation.email, is_active=True).exists():
            state = "log_in"
        else:
            state = "sign_up"
    if request.method == "POST":
        if state != "accept":
            raise Http404
        invitations.accept(invitation, request.user)
        messages.success(request, _("Welcome to the organisation's team."))
        return redirect("manage_home")
    roles = [organisation_people.ROLE_LABELS.get(role, role) for role in invitation.roles] if invitation else []
    return render(
        request,
        "accounts/invitation.html",
        {"invitation": invitation, "state": state, "roles": roles, "token": token},
    )


def organisation_invitation_sign_up(request, token):
    """Create your own account from an invitation: the invited address, your
    name and password; then the invitation is accepted and you're in."""
    from .provisioning import unique_username

    invitation = invitations.find(token)
    if invitation is None or not invitation.is_pending or request.user.is_authenticated:
        return redirect("organisation_invitation", token=token)
    if User.objects.filter(email__iexact=invitation.email).exists():
        return redirect("organisation_invitation", token=token)
    form = InvitedSignUpForm(
        request.POST or None,
        initial={"name": invitation.name, "preferred_language": invitation.language or _site_language(request)},
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        first_name, _sep, last_name = data["name"].partition(" ")
        account = User(
            username=unique_username(slugify(data["name"])),
            email=invitation.email,
            first_name=first_name,
            last_name=last_name,
            phone=data["phone"],
            preferred_language=data["preferred_language"] or _site_language(request),
        )
        account.set_password(data["password"])
        with transaction.atomic():
            account.save()
            invitations.accept(invitation, account)
        auth_login(request, account, backend="accounts.backends.EmailOrUsernameBackend")
        messages.success(request, _("Welcome to the organisation's team."))
        return redirect("manage_home")
    return render(request, "accounts/invitation_sign_up.html", {"invitation": invitation, "form": form})
