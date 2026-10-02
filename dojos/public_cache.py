"""A dojo's public page, cached per dojo (core.caching, CAPACITY.md
"Caching"): the dojo with its pathways, its FAQs, its latest updates and its
team listing. The next session (its places change with every booking) and
the visitor's own join button stay live.

Cleared, now and on commit, whenever what it shows changes: the dojo, its
pathways, its team (memberships, and a member's own team-page profile), its
updates and FAQs. A change that concerns every dojo (a pathway's name, any
FAQ, since site-wide ones show on every dojo's page) clears them all."""

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
TEAM_FIELDS = ["id", "dojo", "user", "role", "status"] + [
    f"user__{name}" for name in ("id", "account_type", "username", *sorted(PROFILE_FIELDS))
]


def detail(dojo_id):
    """{"dojo", "faqs", "announcements", "mentors"} for a public dojo, or a 404."""
    from content.models import FAQ

    from .models import Dojo
    from .views import PUBLIC_UPDATES_LIMIT

    def build():
        dojo = get_object_or_404(Dojo.objects.public().prefetch_related("pathways"), id=dojo_id)
        return {
            "dojo": dojo,
            "faqs": list(FAQ.objects.for_dojo(dojo).select_related("dojo")),
            "announcements": list(dojo.announcements.all()[:PUBLIC_UPDATES_LIMIT]),
            "mentors": list(dojo.memberships.for_team_page().only(*TEAM_FIELDS)),
        }

    return cached(KEY.format(dojo_id=dojo_id), build, TIMEOUT, name="dojos:detail")


def clear(*dojo_ids):
    keys = [KEY.format(dojo_id=dojo_id) for dojo_id in dojo_ids if dojo_id]
    if keys:
        cache.delete_many(keys)
        transaction.on_commit(lambda: cache.delete_many(keys))


def clear_all():
    pattern = KEY.format(dojo_id="*")
    cache.delete_pattern(pattern)
    transaction.on_commit(lambda: cache.delete_pattern(pattern))


def connect():
    from django.contrib.auth import get_user_model

    from content.models import FAQ, Announcement
    from pathways.models import Pathway

    from .models import Dojo, DojoMembership

    def dojo_changed(sender, instance, **kwargs):
        clear(instance.pk)

    def pathways_changed(sender, instance, action, reverse, pk_set, **kwargs):
        if not action.startswith("post_"):
            return
        if reverse:  # changed from the pathway's side
            clear(*(pk_set or ()))
        else:
            clear(instance.pk)

    def by_dojo_id(sender, instance, **kwargs):
        clear(instance.dojo_id)

    def everywhere(sender, **kwargs):
        clear_all()

    def profile_changed(sender, instance, update_fields=None, **kwargs):
        if update_fields is not None and not PROFILE_FIELDS & set(update_fields):
            return
        clear(*DojoMembership.objects.filter(user=instance).values_list("dojo_id", flat=True))

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
    m2m_changed.connect(
        pathways_changed, sender=Dojo.pathways.through, weak=False, dispatch_uid="dojos.detail.dojo-pathways"
    )
