"""What the navigation shows about the logged-in account (CAPACITY.md,
"Caching"): whether it's an approved champion or mentor, what it applied
for, its organisation roles, the organisation dashboard's areas it may open
and the dojos it manages. The nav (`accounts.context_processors.user_roles`)
and the management area's switcher (`accounts.manage_nav`) read it on every page,
so it's worked out once per request and kept in the cache per account.

**Only the navigation reads it, never an access check.** A stale value can
show or hide a link for a few minutes at most; the pages behind the links
still check with the database (`dojos.access`, `accounts.organisation.require_area`,
`accounts.manage_nav.require_organisation_context`), so it can never open
anything.

It's cleared, now and again on commit, whenever what it's built from
changes: the account itself (saving it, its groups and permissions), its
applications, dojo memberships and organisation roles, and a dojo its team
manages. A change to a group's permissions (a migration, the Django admin)
isn't followed: the timeout covers it. The key includes whether the
background check is valid at this moment, so a check that lapses changes it
without any save.
"""

from dataclasses import dataclass, field

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

CACHE_TIMEOUT = 300


@dataclass
class AccountNavigation:
    approved_champion: bool = False
    approved_mentor: bool = False
    applied_kinds: frozenset = frozenset()  # Application kinds pending or approved
    organisation_roles: frozenset = frozenset()  # OrganisationRole roles
    areas: list = field(default_factory=list)  # accounts.organisation.Area values, in the sidebar's order
    dojos: list = field(default_factory=list)  # every dojo it manages (dojos.access.accessible_dojos), by name

    @property
    def admin_dojo(self):
        return self.dojos[0] if self.dojos else None


def _key(user_id, check_valid):
    return f"accounts:navigation:{user_id}:{int(check_valid)}"


def build(user):
    """AccountNavigation for `user`, from the database."""
    from applications.services import is_approved_champion, is_approved_mentor
    from dojos.access import accessible_dojos

    from .organisation import areas_of

    if not user.is_authenticated:
        return AccountNavigation()
    return AccountNavigation(
        approved_champion=is_approved_champion(user),
        approved_mentor=is_approved_mentor(user),
        applied_kinds=frozenset(user.applications.exclude(status="rejected").values_list("kind", flat=True)),
        organisation_roles=frozenset(user.organisation_roles.values_list("role", flat=True)),
        areas=areas_of(user),
        dojos=list(accessible_dojos(user)),
    )


def for_user(user):
    """AccountNavigation for `user`, from the cache when it's there."""
    if not user.is_authenticated:
        return AccountNavigation()
    key = _key(user.pk, user.background_check_valid)
    navigation = cache.get(key)
    if navigation is None:
        navigation = build(user)
        cache.set(key, navigation, CACHE_TIMEOUT)
    return navigation


def for_request(request):
    """for_user() for the request's account, once per request."""
    if not hasattr(request, "_account_navigation"):
        request._account_navigation = for_user(request.user)
    return request._account_navigation


def clear(*user_ids):
    """Forget the cached navigation of these accounts: now, and again once
    the current transaction commits (a request in between could cache the
    old rows)."""
    keys = [_key(user_id, valid) for user_id in user_ids if user_id for valid in (False, True)]
    if not keys:
        return
    cache.delete_many(keys)
    transaction.on_commit(lambda: cache.delete_many(keys))


def _connect():
    from django.contrib.auth import get_user_model

    from applications.models import Application
    from dojos.models import Dojo, DojoMembership

    from .models import OrganisationRole

    User = get_user_model()

    @receiver(post_save, sender=User, weak=False, dispatch_uid="navigation_user")
    @receiver(post_delete, sender=User, weak=False, dispatch_uid="navigation_user_delete")
    def user_changed(sender, instance, **kwargs):
        clear(instance.pk)

    @receiver(m2m_changed, sender=User.groups.through, weak=False, dispatch_uid="navigation_groups")
    @receiver(m2m_changed, sender=User.user_permissions.through, weak=False, dispatch_uid="navigation_permissions")
    def permissions_changed(sender, instance, action, reverse, pk_set, **kwargs):
        if not action.startswith("post_"):
            return
        if reverse:  # changed from the group's or permission's side
            clear(*(pk_set or ()))
        else:
            clear(instance.pk)

    @receiver(post_save, sender=Application, weak=False, dispatch_uid="navigation_application")
    @receiver(post_delete, sender=Application, weak=False, dispatch_uid="navigation_application_delete")
    def application_changed(sender, instance, **kwargs):
        clear(instance.account_id)

    @receiver(post_save, sender=OrganisationRole, weak=False, dispatch_uid="navigation_role")
    @receiver(post_delete, sender=OrganisationRole, weak=False, dispatch_uid="navigation_role_delete")
    def role_changed(sender, instance, **kwargs):
        clear(instance.account_id)

    @receiver(post_save, sender=DojoMembership, weak=False, dispatch_uid="navigation_membership")
    @receiver(post_delete, sender=DojoMembership, weak=False, dispatch_uid="navigation_membership_delete")
    def membership_changed(sender, instance, **kwargs):
        clear(instance.user_id)

    @receiver(post_save, sender=Dojo, weak=False, dispatch_uid="navigation_dojo")
    def dojo_changed(sender, instance, **kwargs):
        # Its name or kind shows in the switcher of everyone on its team.
        clear(*instance.memberships.values_list("user_id", flat=True))
