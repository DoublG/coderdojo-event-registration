from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _refresh_organisation_groups(sender, **kwargs):
    # A migrate (so every deploy) brings the role groups' permissions up to
    # date, including permissions on models added since the groups were
    # made. Runs after each app's migrations: the last run sees every
    # app's permissions. Cheap and idempotent.
    from .organisation import ensure_groups

    ensure_groups()


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self):
        from core.image_library import register_library

        from . import (
            navigation,
            organisation,  # noqa: F401 — connects the role → staff/group signals
            reauth,  # noqa: F401 — records each login's time in the session
            sign_in,  # noqa: F401 — clears the cached sign-in policy when it changes
            two_step,  # noqa: F401 — connects the "backup code used" mail
        )
        from .template_avatars import TEMPLATE_AVATARS_DIR, TEMPLATE_KID_AVATARS_DIR

        register_library("mentors", TEMPLATE_AVATARS_DIR)
        register_library("ninjas", TEMPLATE_KID_AVATARS_DIR)
        navigation._connect()
        post_migrate.connect(_refresh_organisation_groups, dispatch_uid="accounts.refresh_organisation_groups")
