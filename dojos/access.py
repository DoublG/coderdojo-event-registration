"""Who may use a dojo's admin area (dojos/templates/dojos/_admin_base.html),
and what they may do there.

Access comes from an **active** dojo membership (dojos.DojoMembership) in
one of the two managing roles, held by an account whose background check
is valid:

- CHAMPION — the dojo's owner; exactly one per dojo.
- MENTOR — an adult helper on the dojo's team.

Youth mentors (ninjas helping at sessions) are on the team and the team
pages, but never get admin access: the dashboard shows other children's
details. Requested and dormant memberships grant nothing.

Each role maps to a set of capabilities (ROLE_CAPABILITIES). Views ask for
the capability they need via require_dojo_access(); templates check
`dojo_access.can_<capability>` to hide what the viewer can't use. To
restrict mentors, remove capabilities from ROLE_CAPABILITIES[MENTOR] —
nothing else needs to change. Transferring the champion role is never a
capability: only the champion can do it (DojoAccess.is_champion).
"""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404

from .models import Dojo, DojoMembership

CHAMPION = DojoMembership.CHAMPION
MENTOR = DojoMembership.MENTOR
ROLE_LABELS = {CHAMPION: "Champion", MENTOR: "Mentor"}

# Capabilities. Every role with *any* access can open the dashboard, see
# the events list and use the notification bell; these gate the rest.
TAKE_ATTENDANCE = "take_attendance"
MANAGE_EVENTS = "manage_events"  # create/edit events, change their status
EDIT_SETTINGS = "edit_settings"  # dojo_manage (the dojo's public profile)
MANAGE_TEAM = "manage_team"  # accept/decline join requests, add/remove mentors, promote youth mentors
AWARD_BELTS = "award_belts"  # award a ninja a belt (redesign phase 5)
MANAGE_LIFECYCLE = "manage_lifecycle"  # launch / dormant / archive / reopen the dojo
ALL_CAPABILITIES = frozenset({
    TAKE_ATTENDANCE, MANAGE_EVENTS, EDIT_SETTINGS, MANAGE_TEAM, AWARD_BELTS, MANAGE_LIFECYCLE,
})

ROLE_CAPABILITIES = {
    CHAMPION: ALL_CAPABILITIES,
    # Mentors can do everything for day-to-day running and team management;
    # the dojo's lifecycle (launching it, making it dormant, archiving,
    # reopening) stays with its champion.
    MENTOR: ALL_CAPABILITIES - {MANAGE_LIFECYCLE},
}


@dataclass(frozen=True)
class DojoAccess:
    dojo: Dojo
    role: str
    membership: DojoMembership

    @property
    def role_label(self):
        return ROLE_LABELS[self.role]

    @property
    def is_champion(self):
        return self.role == CHAMPION

    def can(self, capability):
        return capability in ROLE_CAPABILITIES[self.role]

    # Template-friendly shortcuts (templates can't call can() with an argument).
    @property
    def can_take_attendance(self):
        return self.can(TAKE_ATTENDANCE)

    @property
    def can_manage_events(self):
        return self.can(MANAGE_EVENTS)

    @property
    def can_edit_settings(self):
        return self.can(EDIT_SETTINGS)

    @property
    def can_manage_team(self):
        return self.can(MANAGE_TEAM)

    @property
    def can_award_belts(self):
        return self.can(AWARD_BELTS)

    @property
    def can_manage_lifecycle(self):
        return self.can(MANAGE_LIFECYCLE)


def managing_membership(user, dojo):
    """The user's active champion/mentor membership at `dojo`, or None —
    also None when their background check isn't valid."""
    if not user.is_authenticated or not user.background_check_valid:
        return None
    return dojo.memberships.managers().filter(user=user).first()


def dojo_role(user, dojo):
    """CHAMPION, MENTOR or None."""
    membership = managing_membership(user, dojo)
    return membership.role if membership else None


def accessible_dojos(user):
    """Every dojo whose admin area this user may open, by name — what the
    admin sidebar's dojo switcher lists. Includes draft/dormant/archived
    dojos: their team still needs to set them up or bring them back."""
    if not user.is_authenticated or not user.background_check_valid:
        return Dojo.objects.none()
    return (
        Dojo.objects.filter(
            memberships__user=user,
            memberships__status=DojoMembership.ACTIVE,
            memberships__role__in=DojoMembership.MANAGER_ROLES,
        )
        .distinct()
        .order_by("name")
    )


def require_dojo_access(request, dojo_id, capability=None):
    """The one way an admin-area view resolves its dojo. No role at all is a
    404, not a 403, so a guessed id doesn't even confirm another dojo
    exists (same reasoning as accounts._get_own_ninja). A role that lacks
    `capability` is a 403: they already know the dojo, they just can't do
    this part."""
    dojo = get_object_or_404(Dojo, id=dojo_id)
    membership = managing_membership(request.user, dojo)
    if membership is None:
        raise Http404
    access = DojoAccess(dojo=dojo, role=membership.role, membership=membership)
    if capability is not None and not access.can(capability):
        raise PermissionDenied
    return access


def is_approved_mentor(user):
    """Whether `user` may ask to join a dojo's team, or be added to one.
    Until the redesign's onboarding phase lands (one account-level
    Application), "approved" means holding the HelperAccount or DojoOwner
    role from an approved application — this is the one place to change
    when that happens."""
    if not user.is_authenticated or user.is_ninja or not user.background_check_valid:
        return False
    return hasattr(user, "helperaccount") or hasattr(user, "dojoowner")
