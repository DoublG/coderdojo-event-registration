from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "events"

    def ready(self):
        from pathlib import Path

        from core.image_library import register_library

        from . import signals  # noqa: F401
        from .template_images import TEMPLATE_IMAGES_DIR

        register_library("events", TEMPLATE_IMAGES_DIR)
        register_library("awards", Path(__file__).resolve().parent / "seed_data" / "awards")
