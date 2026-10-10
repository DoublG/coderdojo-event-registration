"""A dojo's public page, cached per dojo (core.caching, CAPACITY.md
"Caching"): the dojo with its pathways, its FAQs, its latest updates and its
team listing. The next session (its places change with every booking) and
the visitor's own join button stay live.

Cleared, now and on commit, whenever what it shows changes: the dojo, its
pathways, its team (memberships, and a member's own team-page profile), its
updates and FAQs. A change that concerns every dojo (a pathway's name, any
FAQ, since site-wide ones show on every dojo's page) clears them all."""

from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.shortcuts import get_object_or_404

from core.caching import cached

KEY = "dojos:detail:{dojo_id}"
TIMEOUT = 600
# A team member's fields the team listing shows (accounts.User's team-page
# profile): a save that touches none of them (a login's last_login) leaves
# the cache alone.
PROFILE_FIELDS = {"display_name", "title", "bio", "photo", "show_on_team_pages", "first_name", "last_name"}
# Only what the listing shows goes into the cache, never a member's email
# address or password hash.
TEAM_FIELDS = (
    ["id", "dojo", "user", "role", "status"]
    + [f"user__{name}" for name in ("id", "account_type", "username", *sorted(PROFILE_FIELDS))]
    + ["user__ninja__id", "user__ninja__account", "user__ninja__photo"]
)


def detail(dojo_id: int) -> dict[str, Any]:
    """{"dojo", "faqs", "announcements", "mentors"} for a public dojo, or a 404."""
    from content.models import FAQ

    from .models import Dojo
    from .views import PUBLIC_UPDATES_LIMIT

    def build() -> dict[str, Any]:
        dojo = get_object_or_404(Dojo.objects.public().prefetch_related("pathways"), id=dojo_id)
        return {
            "dojo": dojo,
            "faqs": list(FAQ.objects.for_dojo(dojo).select_related("dojo")),
            "announcements": list(dojo.announcements.all()[:PUBLIC_UPDATES_LIMIT]),
            "mentors": list(dojo.memberships.for_team_page().only(*TEAM_FIELDS)),
        }

    return cached(KEY.format(dojo_id=dojo_id), build, TIMEOUT, name="dojos:detail")


def clear(*dojo_ids: int | None) -> None:
    keys = [KEY.format(dojo_id=dojo_id) for dojo_id in dojo_ids if dojo_id]
    if keys:
        cache.delete_many(keys)
        transaction.on_commit(lambda: cache.delete_many(keys))


def clear_all() -> None:
    pattern = KEY.format(dojo_id="*")
    # delete_pattern is django-redis's own (CACHES), not in Django's cache API.
    cache.delete_pattern(pattern)  # type: ignore[attr-defined]
    transaction.on_commit(lambda: cache.delete_pattern(pattern))  # type: ignore[attr-defined]


def connect() -> None:
    from django.contrib.auth import get_user_model

    from accounts.models import Ninja
    from content.models import FAQ, Announcement
    from pathways.models import Pathway

    from .models import Dojo, DojoMembership

    def dojo_changed(sender: Any, instance: Dojo, **kwargs: Any) -> None:
        clear(instance.pk)

    def pathways_changed(
        sender: Any, instance: Any, action: str, reverse: bool, pk_set: set[int] | None, **kwargs: Any
    ) -> None:
        if not action.startswith("post_"):
            return
        if reverse:  # changed from the pathway's side
            clear(*(pk_set or ()))
        else:
            clear(instance.pk)

    def by_dojo_id(sender: Any, instance: Any, **kwargs: Any) -> None:
        clear(instance.dojo_id)

    def everywhere(sender: Any, **kwargs: Any) -> None:
        clear_all()

    def profile_changed(sender: Any, instance: Any, update_fields: Any = None, **kwargs: Any) -> None:
        if update_fields is not None and not PROFILE_FIELDS & set(update_fields):
            return
        clear(*DojoMembership.objects.filter(user=instance).values_list("dojo_id", flat=True))

    def ninja_avatar_changed(sender: Any, instance: Ninja, update_fields: Any = None, **kwargs: Any) -> None:
        # A youth mentor's avatar on the team listing is the child's own
        # (DojoMembership.photo).
        if not instance.account_id or (update_fields is not None and "photo" not in update_fields):
            return
        clear(*DojoMembership.objects.filter(user_id=instance.account_id).values_list("dojo_id", flat=True))

    for signal in (post_save, post_delete):
        signal.connect(dojo_changed, sender=Dojo, weak=False, dispatch_uid=f"dojos.detail.dojo.{signal is post_save}")
        signal.connect(
            by_dojo_id, sender=DojoMembership, weak=False, dispatch_uid=f"dojos.detail.team.{signal is post_save}"
        )
        signal.connect(
            by_dojo_id, sender=Announcement, weak=False, dispatch_uid=f"dojos.detail.updates.{signal is post_save}"
        )
        # A site-wide FAQ shows on every dojo's page, and an FAQ can move
        # between dojos: rare enough to clear them all.
        signal.connect(everywhere, sender=FAQ, weak=False, dispatch_uid=f"dojos.detail.faqs.{signal is post_save}")
        signal.connect(
            everywhere, sender=Pathway, weak=False, dispatch_uid=f"dojos.detail.pathways.{signal is post_save}"
        )
    post_save.connect(profile_changed, sender=get_user_model(), weak=False, dispatch_uid="dojos.detail.profile")
    post_save.connect(ninja_avatar_changed, sender=Ninja, weak=False, dispatch_uid="dojos.detail.ninja-avatar")
    m2m_changed.connect(
        pathways_changed, sender=Dojo.pathways.through, weak=False, dispatch_uid="dojos.detail.dojo-pathways"
    )
