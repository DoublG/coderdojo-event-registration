"""A dojo's team in its admin area: the Members page, the Team page and every
action posted from it (TEAM_ACTIONS); the rules are dojos.team."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from accounts.models import Ninja, User
from events.models import NinjaEngagement

from .. import team
from ..access import require_dojo_access
from ..forms import (
    AddMentorForm,
    PromoteYouthMentorForm,
    TransferChampionForm,
)
from ..models import DojoMembership
from .common import _admin_context


def _youth_mentor_candidates(dojo):
    """Ninja accounts that can be promoted to youth mentor here: ninjas with
    their own (switched-on) login whose home dojo this is, or who've signed
    up for one of its sessions, and who aren't already on the team."""
    on_team = dojo.memberships.active().values("user_id")
    ninjas = (
        Ninja.objects.exclude(account=None)
        .filter(account__is_active=True)
        .filter(Q(home_dojo=dojo) | Q(registration__event__dojo=dojo))
        .exclude(account_id__in=on_team)
        .select_related("account")
        .distinct()
        .order_by("name")
    )
    return ninjas


@login_required
def dojo_members(request, dojo_id):
    """The admin sidebar's "Members" page: the children whose home dojo this
    is (accounts.home_dojo), with their belt, how they come (the engagement
    snapshot), their own login and youth mentor role. With MANAGE_TEAM, a
    child with a login can be promoted to youth mentor from here (posted to
    dojo_team_action). Children visiting from another dojo show up on each
    session's attendance list instead."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    ninjas = list(
        Ninja.objects.filter(home_dojo=dojo).select_related("account").prefetch_related("belts__belt").order_by("name")
    )
    engagement = {row.ninja_id: row for row in NinjaEngagement.objects.filter(dojo=dojo, ninja__in=ninjas)}
    youth_mentor_ids = set(
        dojo.memberships.active().filter(role=DojoMembership.YOUTH_MENTOR).values_list("user_id", flat=True)
    )
    candidate_ids = (
        set(_youth_mentor_candidates(dojo).values_list("id", flat=True)) if access.can_manage_team else set()
    )
    rows = [
        {
            "ninja": ninja,
            "engagement": engagement.get(ninja.id),
            "has_login": bool(ninja.account_id and ninja.account.is_active),
            "is_youth_mentor": ninja.account_id in youth_mentor_ids,
            "can_promote": ninja.id in candidate_ids,
        }
        for ninja in ninjas
    ]
    return render(
        request,
        "dojos/dojo_members.html",
        {
            "rows": rows,
            "active": "members",
            **_admin_context(request, access),
        },
    )


@login_required
def dojo_team_manage(request, dojo_id):
    """The admin sidebar's "Team" page: the dojo's team, pending join
    requests, and (for MANAGE_TEAM) the forms to act on them."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    memberships = dojo.memberships.select_related("user", "promoted_by__user")
    transfer_candidates = memberships.filter(
        status=DojoMembership.ACTIVE,
        role=DojoMembership.MENTOR,
    ).order_by("user__first_name")
    youth_mentor_candidates = _youth_mentor_candidates(dojo) if access.can_manage_team else Ninja.objects.none()
    return render(
        request,
        "dojos/dojo_team_manage.html",
        {
            "active_members": memberships.filter(status=DojoMembership.ACTIVE).order_by("role", "user__first_name"),
            "requests": memberships.filter(status=DojoMembership.REQUESTED).order_by("created_at"),
            "former_members": memberships.filter(status=DojoMembership.DORMANT).order_by("-left_at"),
            "transfer_candidates": transfer_candidates,
            "youth_mentor_candidates": youth_mentor_candidates,
            "add_mentor_form": AddMentorForm(),
            "promote_form": PromoteYouthMentorForm(candidates=youth_mentor_candidates),
            "transfer_form": TransferChampionForm(candidates=transfer_candidates),
            "active": "team",
            **_admin_context(request, access),
        },
    )


def _team_leave(request, access, membership):
    team.leave(access.membership)
    messages.success(request, _("You've left the %(dojo)s team.") % {"dojo": access.dojo.name})
    return redirect("account_home")


def _team_transfer(request, access, membership):
    if not access.is_champion or membership is None:
        raise PermissionDenied
    team.transfer_champion(access.dojo, access.membership, membership)
    messages.success(
        request,
        _("%(membership)s is now the champion of %(dojo)s.")
        % {"membership": membership.name, "dojo": access.dojo.name},
    )
    return redirect("dojo_team_manage", dojo_id=access.dojo.id)


def _team_accept(request, access, membership):
    team.accept_request(membership, by=request.user)
    messages.success(request, _("%(membership)s is now on the team.") % {"membership": membership.name})


def _team_decline(request, access, membership):
    team.decline_request(membership, by=request.user)
    messages.success(request, _("Request declined."))


def _team_remove(request, access, membership):
    team.remove_member(membership)
    messages.success(request, _("%(membership)s has been removed from the team.") % {"membership": membership.name})


def _team_add_mentor(request, access, membership):
    form = AddMentorForm(request.POST)
    user = None
    if form.is_valid():
        user = User.objects.filter(email__iexact=form.cleaned_data["email"]).first()
    if user is None:
        raise team.TeamError(_("No account uses that email address."))
    team.add_mentor(access.dojo, user, by=request.user)
    messages.success(request, _("%(name)s has been added to the team.") % {"name": user.team_name})


def _team_promote(request, access, membership):
    form = PromoteYouthMentorForm(request.POST, candidates=_youth_mentor_candidates(access.dojo))
    if not form.is_valid():
        raise Http404
    ninja = form.cleaned_data["ninja_id"]
    team.promote_youth_mentor(access.dojo, ninja.account, by_membership=access.membership)
    messages.success(request, _("%(name)s is now a youth mentor.") % {"name": ninja.account.team_name})


# The Team page's actions: handler, whether it needs MANAGE_TEAM, whether it
# needs the posted membership. A handler returns a response, or None to go
# back to the page it came from. Leaving is open to any team manager, the
# transfer is the champion's (checked in its handler).
TEAM_ACTIONS = {
    "leave": (_team_leave, False, False),
    "transfer": (_team_transfer, False, False),
    "accept": (_team_accept, True, True),
    "decline": (_team_decline, True, True),
    "remove": (_team_remove, True, True),
    "add_mentor": (_team_add_mentor, True, False),
    "promote": (_team_promote, True, False),
}


@login_required
def dojo_team_action(request, dojo_id):
    """Every change posted from the Team page (POST only; `action` says which,
    TEAM_ACTIONS): accept / decline a request, add a mentor (by email),
    promote a ninja to youth mentor, remove a member, leave, and transfer
    the champion role."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    if request.method != "POST":
        return redirect("dojo_team_manage", dojo_id=dojo.id)

    membership = None
    if request.POST.get("membership_id"):
        membership = get_object_or_404(DojoMembership, id=request.POST["membership_id"], dojo=dojo)
    handler, needs_team_right, needs_membership = TEAM_ACTIONS.get(request.POST.get("action", ""), (None, True, False))
    try:
        if needs_team_right and not access.can_manage_team:
            raise PermissionDenied
        if needs_membership and membership is None:
            raise Http404
        if handler is None:
            messages.error(request, _("Unknown action."))
        elif (response := handler(request, access, membership)) is not None:
            return response
    except team.TeamError as error:
        messages.error(request, str(error))
    # The Members page posts its "Promote" here too, and comes back to itself.
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("dojo_team_manage", dojo_id=dojo.id)
