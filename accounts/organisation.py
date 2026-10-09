"""Organisation roles (accounts.OrganisationRole): who may use the
organisation's management dashboards, which for now are the Django admin
(DATA_MODEL.md §10, decision 4). Each role is a Django group with the
permissions below. A role opens the organisation dashboard's areas all the
time, but the Django admin only while its holder has asked for it, 12 hours
at a time (accounts.admin_access, DATA_MODEL.md §23).

- BOARD: read-only oversight (dojos, teams, events, applications, badges
  and belts) plus maintaining the organisation's team listing
  (content.OrganisationTeamMember). Deliberately no personal data of
  families (accounts, ninjas, registrations) and no background checks.
- ADMIN: everything the board has, plus editing dojos and events, the site
  content (FAQs, testimonials, announcements), the pathway, badge and
  belt catalogues, the mail templates, campaigns and segments (run day to
  day from the organisation dashboard, /manage/: every area but
  Volunteers), plus viewing sent mail (DATA_MODEL.md §11:
  the board gets no mailing access, since segments and sent mail show
  families' personal data).

- REVIEWER: reviews background checks and decides applications
  (DATA_MODEL.md §21), on the organisation dashboard's Volunteers area
  and in the Django admin. Combinable with the others.

No role can award belts (only a dojo's active champion/mentors can,
events.awards). Only the reviewer role reviews background checks
(applications.can_review_background_checks; a permission granted by hand
before the role existed still counts, see is_reviewer).

Which organisation dashboard pages a role opens is by *area* (DATA_MODEL.md
§23): one permission per group of the dashboard's sidebar (`AREA_PERMISSIONS`),
held through the role groups like any other permission and checked with
`require_area`. Since it's `has_perm`, an area granted by hand counts too,
and a superuser opens every area.

`sync_organisation_access` is called by signals whenever a role is granted
or revoked; it's also safe to call by hand.
"""

from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.http import HttpRequest
from django.utils.translation import gettext_lazy

from .models import OrganisationRole

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser

    from .models import User

    AnyUser = User | AnonymousUser

GROUP_NAMES = {
    OrganisationRole.BOARD: "Organisation: board",
    OrganisationRole.ADMIN: "Organisation: admin",
    OrganisationRole.REVIEWER: "Organisation: background-check reviewer",
}

REVIEW_PERMISSION = "applications.can_review_background_checks"


class Area:
    """The organisation dashboard's areas (DATA_MODEL.md §23), in the order
    the sidebar shows them; /manage/ opens the first one an account has."""

    COMMUNICATION = "communication"  # campaigns, journeys, segments, mail templates, the mail queue
    VOLUNTEERS = "volunteers"  # background checks and applications (§21)
    PUBLIC_SITE = "public_site"  # promotions and sponsors
    NINJAS = "ninjas"  # awards
    PRIVACY = "privacy"  # a person's data: export, deletion, email change
    SECURITY = "security"  # the sign-in policy
    PEOPLE = "people"  # who holds which organisation role (accounts.organisation_people)
    AUDIT_LOG = "audit_log"  # the audit log, read-only (pages.audit_views, DATA_MODEL.md §14)


AREA_PERMISSIONS = {
    Area.COMMUNICATION: "accounts.manage_communication",
    # The review permission itself, so one granted by hand keeps working.
    Area.VOLUNTEERS: REVIEW_PERMISSION,
    Area.PUBLIC_SITE: "accounts.manage_public_site",
    Area.NINJAS: "accounts.manage_ninjas",
    Area.PRIVACY: "accounts.manage_privacy",
    Area.SECURITY: "accounts.manage_security",
    Area.PEOPLE: "accounts.manage_people",
    # The audit log's own view permission (core.audit.AUDIT_LOG_PERMISSION),
    # which the admin role already holds for the Django admin's log.
    Area.AUDIT_LOG: "auditlog.view_logentry",
}

# The areas as the People pages name them (DATA_MODEL.md §23).
AREA_LABELS = {
    Area.COMMUNICATION: gettext_lazy("Communication: campaigns, journeys, segments, mail templates, mail queue"),
    Area.VOLUNTEERS: gettext_lazy("Volunteers: background checks, applications"),
    Area.PUBLIC_SITE: gettext_lazy("Public site: promotions, sponsors"),
    Area.NINJAS: gettext_lazy("Ninjas: awards"),
    Area.PRIVACY: gettext_lazy("Privacy: data export, account deletion, email changes"),
    Area.SECURITY: gettext_lazy("Sign-in security"),
    Area.PEOPLE: gettext_lazy("People: organisation roles"),
    Area.AUDIT_LOG: gettext_lazy("Audit log: who changed what (read-only)"),
}

_VIEW = ["view"]
_EDIT = ["add", "change", "delete", "view"]

BOARD_PERMISSIONS = {
    "dojos.dojo": _VIEW,
    "dojos.dojomembership": _VIEW,
    "events.event": _VIEW,
    "events.badge": _VIEW,
    "events.belt": _VIEW,
    "events.ninjabadge": _VIEW,
    "events.ninjabelt": _VIEW,
    "applications.application": _VIEW,
    "pathways.pathway": _VIEW,
    "content.organisationteammember": _EDIT,
}
ADMIN_PERMISSIONS = {
    **BOARD_PERMISSIONS,
    "dojos.dojo": ["change", "view"],
    "events.event": ["change", "view"],
    "events.badge": _EDIT,
    "events.belt": _EDIT,
    "content.faq": _EDIT,
    "content.testimonial": _EDIT,
    "content.announcement": _EDIT,
    "pathways.pathway": _EDIT,
    "pathways.pathwaystep": _EDIT,
    "pathways.pathwayproject": _EDIT,
    "pathways.skill": _EDIT,
    "mailing.emailtemplate": _EDIT,
    # Day to day these are run from the organisation dashboard (/manage/);
    # the admin keeps full access for fixing things by hand.
    "campaigns.segment": _EDIT,
    "campaigns.segmentgroup": _EDIT,
    "campaigns.segmentrule": _EDIT,
    "campaigns.campaign": _EDIT,
    "campaigns.journey": _EDIT,
    "campaigns.journeydelivery": _VIEW,
    "mailing.emailmessage": _VIEW,
    "mailing.mailpreference": _VIEW,
    "mailing.consentevent": _VIEW,
    "mailing.emailsuppression": _EDIT,
    "mailing.bouncerecord": _VIEW,
    # The audit log (DATA_MODEL.md §14): the admin role only, never the board.
    "auditlog.logentry": _VIEW,
    # Its organisation dashboard areas (DATA_MODEL.md §23): all but Volunteers.
    "accounts.organisationrole": [
        "manage_communication",
        "manage_public_site",
        "manage_ninjas",
        "manage_privacy",
        "manage_security",
        "manage_people",
    ],
}
# Criminal-record extracts (GDPR art. 10): this role only, never the board or
# the admin role by themselves. An action with an underscore is a whole
# codename (a custom permission) rather than "<action>_<model>".
REVIEWER_PERMISSIONS = {
    "applications.application": ["view", "change", "can_review_background_checks"],
    "applications.backgroundcheck": ["view", "change"],
    "applications.backgroundcheckhistory": _VIEW,
}
ROLE_PERMISSIONS = {
    OrganisationRole.BOARD: BOARD_PERMISSIONS,
    OrganisationRole.ADMIN: ADMIN_PERMISSIONS,
    OrganisationRole.REVIEWER: REVIEWER_PERMISSIONS,
}


def role_areas(role: str) -> list[str]:
    """The areas `role` opens, from ROLE_PERMISSIONS (the Roles page)."""
    held: set[str] = set()
    for model, actions in ROLE_PERMISSIONS[role].items():
        app_label, model_name = model.split(".")
        held |= {f"{app_label}.{a if '_' in a else f'{a}_{model_name}'}" for a in actions}
    return [area for area, perm in AREA_PERMISSIONS.items() if perm in held]


def _permissions(spec: dict[str, list[str]]) -> list[Permission]:
    perms: list[Permission] = []
    for model, actions in spec.items():
        app_label, model_name = model.split(".")
        perms += Permission.objects.filter(
            content_type__app_label=app_label,
            codename__in=[a if "_" in a else f"{a}_{model_name}" for a in actions],
        )
    return perms


def ensure_groups() -> dict[str, Group]:
    """Create/refresh the role groups with exactly their permissions."""
    groups: dict[str, Group] = {}
    for role, name in GROUP_NAMES.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set(_permissions(ROLE_PERMISSIONS[role]))
        groups[role] = group
    return groups


def sync_organisation_access(user: "User") -> None:
    """Put `user` in exactly the groups of the roles they hold. A role no
    longer makes the account staff: the Django admin is asked for, 12 hours
    at a time (accounts.admin_access, DATA_MODEL.md §23), so losing the last
    role ends any access still open."""
    from . import admin_access
    from .models import AdminAccessGrant

    groups = ensure_groups()
    roles = set(user.organisation_roles.values_list("role", flat=True))
    for role, group in groups.items():
        if role in roles:
            user.groups.add(group)
        else:
            user.groups.remove(group)
    if not roles:
        admin_access.end_for(user, end_reason=AdminAccessGrant.ROLE_REMOVED)
    admin_access.sync_staff(user)


def is_organisation_admin(user: "AnyUser") -> bool:
    """Holds the `admin` organisation role. Which dashboard pages that opens
    is a matter of areas (has_area); this is the role itself."""
    return user.is_authenticated and user.organisation_roles.filter(role=OrganisationRole.ADMIN).exists()


def has_area(user: "AnyUser", area: str) -> bool:
    """May open the organisation dashboard's `area` (an `Area`)."""
    return user.is_authenticated and user.has_perm(AREA_PERMISSIONS[area])


def areas_of(user: "AnyUser") -> list[str]:
    """The areas `user` may open, in the sidebar's order."""
    return [area for area in AREA_PERMISSIONS if has_area(user, area)]


def require_area(request: HttpRequest, area: str) -> None:
    """For every view of the organisation dashboard: 404 unless the account
    may open `area` (same no-leak reasoning as dojos.access), and its login
    meets the organisation's sign-in policy (accounts.sign_in)."""
    from django.http import Http404

    from .sign_in import meets_requirement

    if not has_area(request.user, area) or not meets_requirement(request):
        raise Http404


def is_reviewer(user: "AnyUser") -> bool:
    """May review background checks and decide applications (DATA_MODEL.md
    §21): the Volunteers area, i.e. the reviewer role or the permission
    granted some other way (by hand, or a superuser)."""
    return has_area(user, Area.VOLUNTEERS)


@receiver(post_save, sender=OrganisationRole)
@receiver(post_delete, sender=OrganisationRole)
def _role_changed(sender: Any, instance: OrganisationRole, **kwargs: Any) -> None:
    from .models import User

    user = User.objects.filter(pk=instance.account_id).first()
    if user is not None:  # gone when the role was cascade-deleted with its account
        sync_organisation_access(user)
