from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        from . import organisation  # noqa: F401 — connects the role → staff/group signals
