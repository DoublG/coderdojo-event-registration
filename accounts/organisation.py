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

Neither role can award belts (only a dojo's active champion/mentors can,
events.awards) or review background checks (a separate, explicitly granted
permission: applications.can_review_background_checks).

`sync_organisation_access` is called by signals whenever a role is granted
or revoked; it's also safe to call by hand.
"""

from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import OrganisationRole

GROUP_NAMES = {OrganisationRole.BOARD: "Organisation: board", OrganisationRole.ADMIN: "Organisation: admin"}

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
}
ROLE_PERMISSIONS = {OrganisationRole.BOARD: BOARD_PERMISSIONS, OrganisationRole.ADMIN: ADMIN_PERMISSIONS}


def _permissions(spec):
    perms = []
    for model, actions in spec.items():
        app_label, model_name = model.split(".")
        perms += Permission.objects.filter(
            content_type__app_label=app_label, codename__in=[f"{a}_{model_name}" for a in actions],
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
    holds the admin role (same no-leak reasoning as dojos.access)."""
    from django.http import Http404

    if not is_organisation_admin(request.user):
        raise Http404


@receiver(post_save, sender=OrganisationRole)
@receiver(post_delete, sender=OrganisationRole)
def _role_changed(sender, instance, **kwargs):
    from .models import User

    user = User.objects.filter(pk=instance.account_id).first()
    if user is not None:  # gone when the role was cascade-deleted with its account
        sync_organisation_access(user)
