"""Who may use a dojo's admin area (dojos/templates/dojos/_admin_base.html),
and what they may do there.

Two roles have access to a dojo's admin area:

- OWNER — the dojo's own DojoOwner login (Dojo.owner).
- HELPER — a HelperAccount linked to the dojo through its Mentor profile
  (Mentor.helper_account + Mentor.dojo). Only HelperAccount counts: a
  Guardian- or ChildAccount-linked mentor profile never gets admin access,
  since only DojoOwner/HelperAccount go through the background-check
  pipeline (see applications.models.BackgroundCheckMixin).

Each role maps to a set of capabilities (ROLE_CAPABILITIES). Views ask for
the capability they need via require_dojo_access(); templates check
`dojo_access.can_<capability>` to hide what the viewer can't use. To
restrict helpers, remove capabilities from ROLE_CAPABILITIES[HELPER] —
nothing else needs to change.
"""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404

from .models import Dojo, Mentor

OWNER = "owner"
HELPER = "helper"
ROLE_LABELS = {OWNER: "Owner", HELPER: "Helper"}

# Capabilities. Every role with *any* access can open the dashboard, see
# the events list and use the notification bell; these gate the rest.
TAKE_ATTENDANCE = "take_attendance"
MANAGE_EVENTS = "manage_events"  # create/edit events, change their status
EDIT_SETTINGS = "edit_settings"  # dojo_manage (the dojo's public profile)
ALL_CAPABILITIES = frozenset({TAKE_ATTENDANCE, MANAGE_EVENTS, EDIT_SETTINGS})

ROLE_CAPABILITIES = {
    OWNER: ALL_CAPABILITIES,
    # For now helpers can do everything an owner can here.
    HELPER: ALL_CAPABILITIES,
}


@dataclass(frozen=True)
class DojoAccess:
    dojo: Dojo
    role: str

    @property
    def role_label(self):
        return ROLE_LABELS[self.role]

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


def dojo_role(user, dojo):
    """OWNER, HELPER or None. Owner wins if a user somehow holds both.
    HelperAccount shares its pk with the base User (multi-table
    inheritance), so helper_account_id can be compared to user.pk directly."""
    if not user.is_authenticated:
        return None
    if dojo.owner_id == user.pk:
        return OWNER
    if Mentor.objects.filter(dojo=dojo, helper_account_id=user.pk).exists():
        return HELPER
    return None


def accessible_dojos(user):
    """Every dojo whose admin area this user may open, by name — what the
    admin sidebar's dojo switcher lists."""
    if not user.is_authenticated:
        return Dojo.objects.none()
    return (
        Dojo.objects.filter(Q(owner_id=user.pk) | Q(mentors__helper_account_id=user.pk))
        .distinct()
        .order_by("name")
    )


def require_dojo_access(request, dojo_id, capability=None):
    """The one way an admin-area view resolves its dojo. No role at all is a
    404, not a 403, so a guessed id doesn't even confirm another dojo
    exists (same reasoning as accounts._get_own_guardian). A role that
    lacks `capability` is a 403: they already know the dojo, they just
    can't do this part."""
    dojo = get_object_or_404(Dojo, id=dojo_id)
    role = dojo_role(request.user, dojo)
    if role is None:
        raise Http404
    access = DojoAccess(dojo=dojo, role=role)
    if capability is not None and not access.can(capability):
        raise PermissionDenied
    return access
