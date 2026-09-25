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
    name = 'accounts'

    def ready(self):
        from . import organisation  # noqa: F401 — connects the role → staff/group signals

        post_migrate.connect(_refresh_organisation_groups, dispatch_uid="accounts.refresh_organisation_groups")
