from django.apps import AppConfig


class DojosConfig(AppConfig):
    name = "dojos"

    def ready(self):
        from core.image_library import register_library

        from . import public_cache
        from .template_icons import TEMPLATE_ICONS_DIR

        register_library("dojos", TEMPLATE_ICONS_DIR)

        public_cache.connect()  # clears a dojo's cached public page when it changes
