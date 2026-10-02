from django.apps import AppConfig


class ContentConfig(AppConfig):
    name = "content"

    def ready(self):
        from . import cache

        cache.connect()  # clears the cached public lists when their rows change
