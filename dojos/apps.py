from django.apps import AppConfig


class DojosConfig(AppConfig):
    name = "dojos"

    def ready(self):
        from . import public_cache

        public_cache.connect()  # clears a dojo's cached public page when it changes
