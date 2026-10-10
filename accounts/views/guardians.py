"""A child's guardians (DATA_MODEL_PRIVACY.md §27): the *Guardians* card on
the child's page (invite another adult, send an invitation again, withdraw
it, remove a guardian or step down) and the invitation link's page. The
rules are accounts.guardian_invitations'; these only show and call them."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from .. import guardian_invitations
from ..forms import AcceptGuardianInvitationForm, ConfirmIdentityForm, InviteGuardianForm
from ..guardian_invitations import GuardianInvitationError
from ..models import GuardianInvitation, Guardianship, User
from .common import _get_own_ninja


def _guardians_card_context(request, child, form=None, error="", notice=""):
    """What accounts/partials/_guardians_card.html needs: every guardian
    with whether the viewer may remove them, the invitations waiting, and
    the invite form for a parent or legal guardian."""
    can_manage = guardian_invitations.is_responsible(child, request.user)
    links = []
    for link in child.guardianships.select_related("guardian").order_by("created_at"):
        problem = guardian_invitations.removal_problem(link, request.user)
        is_you = link.guardian_id == request.user.pk
        # Offered only to whom it's open: a guardian without parental
        # responsibility sees the list, and steps down from their own link.
        offered = is_you or can_manage
        links.append({"link": link, "is_you": is_you, "can_remove": offered and not problem})
    return {
        "child": child,
        "guardian_links": links,
        "guardian_invitations": list(child.guardian_invitations.pending()) if can_manage else [],
        "can_manage_guardians": can_manage,
        "guardian_form": form or InviteGuardianForm(),
        "guardians_error": error,
        "guardians_notice": notice,
    }


def _guardians_card(request, child, **kwargs):
    """The card for an htmx post, or back to the child's page (the outcome
    as a message) without one."""
    if request.headers.get("HX-Request") == "true":
        return render(
            request, "accounts/partials/_guardians_card.html", _guardians_card_context(request, child, **kwargs)
        )
    if kwargs.get("error"):
        messages.error(request, kwargs["error"])
    elif kwargs.get("notice"):
        messages.success(request, kwargs["notice"])
    return redirect(reverse("ninja_detail", kwargs={"ninja_id": child.id}) + "#guardians-card")


@login_required
def guardian_invite(request, ninja_id):
    child = _get_own_ninja(request, ninja_id)
    if request.method != "POST":
        return redirect("ninja_detail", ninja_id=child.id)
    form = InviteGuardianForm(request.POST)
    if not form.is_valid():
        if request.headers.get("HX-Request") == "true":
            return _guardians_card(request, child, form=form)
        return _guardians_card(request, child, error=_("Enter a valid email address and choose a relation."))
    try:
        invitation = guardian_invitations.invite(
            child, form.cleaned_data["email"], form.cleaned_data["relation"], request.user
        )
    except GuardianInvitationError as problem:
        form.add_error(None, str(problem))
        if request.headers.get("HX-Request") == "true":
            return _guardians_card(request, child, form=form)
        return _guardians_card(request, child, error=str(problem))
    return _guardians_card(
        request,
        child,
        notice=_("We've mailed an invitation to %(email)s. %(name)s's other guardians have been told.")
        % {"email": invitation.email, "name": child.name},
    )


def _own_invitation(request, ninja_id, invitation_id):
    child = _get_own_ninja(request, ninja_id)
    return child, get_object_or_404(GuardianInvitation, pk=invitation_id, ninja=child)


@login_required
def guardian_invitation_resend(request, ninja_id, invitation_id):
    child, invitation = _own_invitation(request, ninja_id, invitation_id)
    if request.method != "POST":
        return redirect("ninja_detail", ninja_id=child.id)
    try:
        guardian_invitations.resend(invitation, request.user)
    except GuardianInvitationError as problem:
        return _guardians_card(request, child, error=str(problem))
    return _guardians_card(
        request, child, notice=_("We've mailed %(email)s a new link.") % {"email": invitation.email}
    )


@login_required
def guardian_invitation_withdraw(request, ninja_id, invitation_id):
    child, invitation = _own_invitation(request, ninja_id, invitation_id)
    if request.method != "POST":
        return redirect("ninja_detail", ninja_id=child.id)
    try:
        guardian_invitations.withdraw(invitation, request.user)
    except GuardianInvitationError as problem:
        return _guardians_card(request, child, error=str(problem))
    return _guardians_card(
        request, child, notice=_("The invitation to %(email)s is withdrawn.") % {"email": invitation.email}
    )


@login_required
def guardian_remove(request, ninja_id, guardianship_id):
    """Remove a guardian, or step down yourself: a page that asks the account
    to confirm it's them (accounts.forms.ConfirmIdentityForm), since it cuts
    someone off from a child."""
    child = _get_own_ninja(request, ninja_id)
    link = get_object_or_404(Guardianship, pk=guardianship_id, ninja=child)
    stepping_down = link.guardian_id == request.user.pk
    problem = guardian_invitations.removal_problem(link, request.user)
    form = ConfirmIdentityForm(request.user, request.POST if request.method == "POST" else None, request=request)
    if request.method == "POST" and not problem and form.is_valid():
        try:
            guardian_invitations.remove(link, request.user)
        except GuardianInvitationError as error:
            problem = str(error)
        else:
            if stepping_down:
                messages.success(request, _("You're no longer %(name)s's guardian.") % {"name": child.name})
                return redirect("account_home")
            messages.success(
                request,
                _("%(guardian)s is no longer %(name)s's guardian. We've let them know.")
                % {"guardian": link.guardian.team_name, "name": child.name},
            )
            return redirect(reverse("ninja_detail", kwargs={"ninja_id": child.id}) + "#guardians-card")
    return render(
        request,
        "accounts/guardian_remove.html",
        {"child": child, "link": link, "stepping_down": stepping_down, "problem": problem, "form": form},
    )


def guardian_invitation(request, token):
    """The link in the invitation mail: who invites you as whose guardian,
    then create an account, log in, or (logged in with the invited address)
    accept. GET shows, POST accepts, so a mail scanner can't accept it."""
    invitation = guardian_invitations.find(token)
    state = "invalid"
    if invitation is not None and guardian_invitations._still_valid(invitation):
        user = request.user
        if user.is_authenticated:
            if invitation.ninja.guardianships.filter(guardian=user).exists():
                state = "already"
            elif guardian_invitations.can_accept(invitation, user):
                state = "accept"
            else:
                state = "other_account"
        elif User.objects.filter(email__iexact=invitation.email, is_active=True).exists():
            state = "log_in"
        else:
            state = "sign_up"
    form = AcceptGuardianInvitationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if state != "accept" or not form.is_valid():
            raise Http404
        try:
            guardian_invitations.accept(invitation, request.user, consent=form.cleaned_data["consent"])
        except GuardianInvitationError as problem:
            messages.error(request, str(problem))
            return redirect("guardian_invitation", token=token)
        messages.success(request, _("You're now %(name)s's guardian.") % {"name": invitation.ninja.name})
        return redirect("ninja_detail", ninja_id=invitation.ninja_id)
    sign_up_url = login_url = ""
    if state in ("sign_up", "log_in"):
        next_query = urlencode({"next": request.path})
        sign_up_url = f"{reverse('register_individual')}?{next_query}"
        login_url = f"{reverse('login')}?{next_query}"
    return render(
        request,
        "accounts/guardian_invitation.html",
        {
            "invitation": invitation,
            "state": state,
            "form": form,
            "may_give_consent": invitation is not None and guardian_invitations.may_give_consent(invitation),
            "sign_up_url": sign_up_url,
            "login_url": login_url,
        },
    )
