"""The management area's contexts (DATA_MODEL.md §20): what an account can
manage, for the switcher at the top of the shared sidebar
(core/_manage_shell.html) and for /manage/'s landing.

Only the navigation is shared. Who may open what stays with the existing
rules: the organisation's pages need the organisation `admin` role, its
Volunteers pages the `reviewer` role (accounts.organisation), and a dojo,
an organisation dojo included, an active champion/mentor membership and a
valid background check (dojos.access). So
an organisation member without a background check gets the Organisation
context only, and no dojos at all.
"""

from dataclasses import dataclass, field

from accounts.organisation import is_organisation_admin, is_reviewer
from dojos.access import accessible_dojos


@dataclass
class ManageContexts:
    organisation_admin: bool = False  # the organisation's dashboard (/manage/…): campaigns, content, ...
    reviewer: bool = False  # its Volunteers pages: background checks and applications (§21)
    organisation_dojos: list = field(default_factory=list)  # organisation dojos on whose team the account is
    dojos: list = field(default_factory=list)  # regular dojos on whose team the account is

    @property
    def organisation(self):
        """The Organisation context opens for either role; its sidebar shows
        each group only to the role that may open it."""
        return self.organisation_admin or self.reviewer

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
        organisation_admin=is_organisation_admin(user),
        reviewer=is_reviewer(user),
        organisation_dojos=[d for d in dojos if d.is_organisation],
        dojos=[d for d in dojos if not d.is_organisation],
    )


def request_manage_contexts(request):
    """manage_contexts for the request's account, worked out once per
    request (the switcher and the Organisation sidebar both read it)."""
    if not hasattr(request, "_manage_contexts"):
        request._manage_contexts = manage_contexts(request.user)
    return request._manage_contexts
