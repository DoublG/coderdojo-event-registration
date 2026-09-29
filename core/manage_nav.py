"""The management area's contexts (DATA_MODEL.md §20): what an account can
manage, for the switcher at the top of the shared sidebar
(core/_manage_shell.html) and for /manage/'s landing.

Only the navigation is shared. Who may open what stays with the existing
rules: each group of the organisation's pages needs its area
(accounts.organisation.require_area, DATA_MODEL.md §23: the `admin` role
opens all but Volunteers, the `reviewer` role Volunteers), and a dojo, an
organisation dojo included, an active champion/mentor membership and a
valid background check (dojos.access). So an organisation member without
a background check gets the Organisation context only, and no dojos at all.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext_lazy as _

from accounts.models import OrganisationRole
from accounts.organisation import areas_of
from dojos.access import accessible_dojos


@dataclass
class ManageContexts:
    areas: list = field(default_factory=list)  # the organisation dashboard's areas it may open (Area, §23)
    organisation_roles: set = field(default_factory=set)  # its OrganisationRole roles, for the sidebar's label
    organisation_dojos: list = field(default_factory=list)  # organisation dojos on whose team the account is
    dojos: list = field(default_factory=list)  # regular dojos on whose team the account is

    @property
    def organisation(self):
        """The Organisation context opens for any area; its sidebar shows
        each group only to an account that may open its area."""
        return bool(self.areas)

    @property
    def can(self):
        """{area: True} for the areas it may open, for templates:
        `{% if contexts.can.communication %}`."""
        return dict.fromkeys(self.areas, True)

    @property
    def organisation_role_label(self):
        """What the Organisation context's sidebar footer calls the account."""
        if OrganisationRole.ADMIN in self.organisation_roles:
            return _("Organisation admin")
        if OrganisationRole.REVIEWER in self.organisation_roles:
            return _("Background-check reviewer")
        return _("Organisation")

    @property
    def count(self):
        return int(self.organisation) + len(self.organisation_dojos) + len(self.dojos)

    @property
    def any(self):
        return self.count > 0

    @property
    def first_dojo(self):
        return (self.dojos or self.organisation_dojos or [None])[0]


def manage_contexts(user):
    """Everything `user` can manage, by group. Worked out from the same
    helpers the views check, so the switcher never offers a page that would
    404."""
    if not user.is_authenticated:
        return ManageContexts()
    dojos = list(accessible_dojos(user))
    return ManageContexts(
        areas=areas_of(user),
        organisation_roles=set(user.organisation_roles.values_list("role", flat=True)),
        organisation_dojos=[d for d in dojos if d.is_organisation],
        dojos=[d for d in dojos if not d.is_organisation],
    )


def request_manage_contexts(request):
    """manage_contexts for the request's account, worked out once per
    request (the switcher and the Organisation sidebar both read it)."""
    if not hasattr(request, "_manage_contexts"):
        request._manage_contexts = manage_contexts(request.user)
    return request._manage_contexts
