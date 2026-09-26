from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class PrivacyConfig(AppConfig):
    name = "privacy"

    def ready(self):
        # Every app declares its models' personal data in its own privacy.py
        # (DATA_MODEL.md §16), picked up here the way Celery finds tasks.py.
        autodiscover_modules("privacy")
