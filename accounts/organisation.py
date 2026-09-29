"""Organisation roles (accounts.OrganisationRole): who may use the
organisation's management dashboards, which for now are the Django admin
(DATA_MODEL.md §10, decision 4). Each role is a Django group with the
permissions below; holding any role makes the account staff.

- BOARD: read-only oversight (dojos, teams, events, applications, badges
  and belts) plus maintaining the organisation's team listing
  (content.OrganisationTeamMember). Deliberately no personal data of
  families (accounts, ninjas, registrations) and no background checks.
- ADMIN: everything the board has, plus editing dojos and events, the site
  content (FAQs, testimonials, announcements), the pathway, badge and
  belt catalogues, the mail templates, campaigns and segments (run day to
  day from the organisation dashboard, /manage/, which only this role
  opens: is_organisation_admin), plus viewing sent mail (DATA_MODEL.md §11:
  the board gets no mailing access, since segments and sent mail show
  families' personal data).

- REVIEWER: reviews background checks and decides applications
  (DATA_MODEL.md §21), on the organisation dashboard's Volunteers pages
  (require_reviewer) and in the Django admin. Combinable with the others.

No role can award belts (only a dojo's active champion/mentors can,
events.awards). Only the reviewer role reviews background checks
(applications.can_review_background_checks; a permission granted by hand
before the role existed still counts, see is_reviewer).

`sync_organisation_access` is called by signals whenever a role is granted
or revoked; it's also safe to call by hand.
"""

from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import OrganisationRole

GROUP_NAMES = {
    OrganisationRole.BOARD: "Organisation: board",
    OrganisationRole.ADMIN: "Organisation: admin",
    OrganisationRole.REVIEWER: "Organisation: background-check reviewer",
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
    "mailing.segment": _EDIT,
    "mailing.segmentgroup": _EDIT,
    "mailing.segmentrule": _EDIT,
    "mailing.campaign": _EDIT,
    "mailing.journey": _EDIT,
    "mailing.journeydelivery": _VIEW,
    "mailing.emailmessage": _VIEW,
    "mailing.mailpreference": _VIEW,
    "mailing.consentevent": _VIEW,
    "mailing.emailsuppression": _EDIT,
    "mailing.bouncerecord": _VIEW,
    # The audit log (DATA_MODEL.md §14): the admin role only, never the board.
    "auditlog.logentry": _VIEW,
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
REVIEW_PERMISSION = "applications.can_review_background_checks"


def _permissions(spec):
    perms = []
    for model, actions in spec.items():
        app_label, model_name = model.split(".")
        perms += Permission.objects.filter(
            content_type__app_label=app_label,
            codename__in=[a if "_" in a else f"{a}_{model_name}" for a in actions],
        )
    return perms


def ensure_groups():
    """Create/refresh the role groups with exactly their permissions."""
    groups = {}
    for role, name in GROUP_NAMES.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.set(_permissions(ROLE_PERMISSIONS[role]))
        groups[role] = group
    return groups


def sync_organisation_access(user):
    """Put `user` in exactly the groups of the roles they hold, and make them
    staff while they hold any. Losing the last role only drops staff status
    when nothing else needs it (superuser, direct permissions or other
    groups — e.g. a background-check reviewer)."""
    groups = ensure_groups()
    roles = set(user.organisation_roles.values_list("role", flat=True))
    for role, group in groups.items():
        if role in roles:
            user.groups.add(group)
        else:
            user.groups.remove(group)

    if roles:
        needs_staff = True
    else:
        needs_staff = (
            user.is_superuser
            or user.user_permissions.exists()
            or user.groups.exclude(name__in=GROUP_NAMES.values()).exists()
        )
    if user.is_staff != needs_staff:
        user.is_staff = needs_staff
        user.save(update_fields=["is_staff"])


def is_organisation_member(user):
    return user.is_authenticated and user.organisation_roles.exists()


def is_organisation_admin(user):
    """Holds the `admin` organisation role: may use the organisation's
    management dashboard (/manage/, e.g. campaigns)."""
    return user.is_authenticated and user.organisation_roles.filter(role=OrganisationRole.ADMIN).exists()


def require_organisation_admin(request):
    """For every view of the organisation dashboard: 404 unless the account
    holds the admin role (same no-leak reasoning as dojos.access), and its
    login meets the organisation's sign-in policy (accounts.sign_in)."""
    from django.http import Http404

    from .sign_in import meets_requirement

    if not is_organisation_admin(request.user) or not meets_requirement(request):
        raise Http404


def is_reviewer(user):
    """May review background checks and decide applications (DATA_MODEL.md
    §21): the reviewer role, or the permission granted some other way (by
    hand, or a superuser)."""
    return user.is_authenticated and user.has_perm(REVIEW_PERMISSION)


def require_reviewer(request):
    """For every Volunteers page of the organisation dashboard and the
    background-check document: 404 unless the account may review, and its
    login meets the organisation's sign-in policy (accounts.sign_in)."""
    from django.http import Http404

    from .sign_in import meets_requirement

    if not is_reviewer(request.user) or not meets_requirement(request):
        raise Http404


@receiver(post_save, sender=OrganisationRole)
@receiver(post_delete, sender=OrganisationRole)
def _role_changed(sender, instance, **kwargs):
    from .models import User

    user = User.objects.filter(pk=instance.account_id).first()
    if user is not None:  # gone when the role was cascade-deleted with its account
        sync_organisation_access(user)
