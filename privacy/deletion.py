"""Deleting an account on request (GDPR art. 17, DATA_MODEL.md §16 phase 5):
by the family itself from its account page, or by the organisation from
its Privacy page for a request by mail or post. Both show `preview()`
first and then call `delete_account()`, which runs the erasure
(`privacy.erasure.erase_person`) the same way the retention job does: a
champion's or mentor's account is cleaned (`keep_visible`), a family's is
erased with the children only it is a guardian of.

What stops it (`Preview.blockers`, each a message for the person asking):
being the champion of an active dojo (the role has to move first), an
organisation role, a superuser, a ninja's own login (it goes with its
family, and only the guardian takes it away) and an API client's technical
account. Views only call these;
`DeletionError` carries the message.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext as _

from accounts.models import Ninja
from privacy.erasure import erase_person, is_erased, sole_children
from privacy.models import ErasureRecord
from privacy.retention import champion_of_active_dojos, is_volunteer


class DeletionError(Exception):
    """A user-facing reason the account can't be deleted (yet)."""


@dataclass
class Preview:
    """What deleting `user` would do."""

    user: object
    # Erased with the account (only this account is their guardian).
    children: list = field(default_factory=list)
    # Stay, with their other guardian.
    shared_children: list = field(default_factory=list)
    # Cleaned instead of erased: their name stays on past sessions.
    volunteer: bool = False
    keeps_profile: bool = False
    blockers: list = field(default_factory=list)

    @property
    def possible(self):
        return not self.blockers


def preview(user):
    if user.is_ninja:
        return Preview(
            user, blockers=[_("A child's own login is removed by their parent, or goes with the family's account.")]
        )
    if user.is_service:
        return Preview(
            user, blockers=[_("This is an API client's technical account: the dojo's champion revokes the client.")]
        )
    children = sole_children(user)
    shared = [child for child in Ninja.objects.of_guardian(user).order_by("name") if child not in children]
    volunteer = is_volunteer(user)
    blockers = []
    if is_erased(user):
        blockers.append(_("This account has already been deleted."))
    if dojos := champion_of_active_dojos(user):
        blockers.append(
            _(
                "This account is the champion of %(dojos)s. A dojo can't be without its champion: the role has to "
                "go to one of the dojo's mentors first (on the dojo's Team page)."
            )
            % {"dojos": ", ".join(dojo.name for dojo in dojos)}
        )
    if user.organisation_roles.exists():
        blockers.append(_("This account has an organisation role. It has to be taken away first."))
    if user.is_superuser:
        blockers.append(_("This is a technical administrator's account (superuser); it can't be deleted here."))
    return Preview(
        user,
        children=sorted(children, key=lambda child: child.name),
        shared_children=shared,
        volunteer=volunteer,
        keeps_profile=volunteer and user.show_on_team_pages,
        blockers=blockers,
    )


def delete_account(user, requested_by=None):
    """Erase (or, for a champion or mentor, clean) `user` now. With
    `requested_by` it's the organisation acting on a request; without, the
    account holder themselves."""
    result = preview(user)
    if not result.possible:
        raise DeletionError(result.blockers[0])
    erase_person(
        user,
        requested_by=requested_by,
        reason=ErasureRecord.REQUEST if requested_by else ErasureRecord.SELF,
        keep_visible=result.volunteer,
    )
    return result
