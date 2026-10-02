from django.apps import AppConfig


class PathwaysConfig(AppConfig):
    name = "pathways"

    def ready(self):
        from pathlib import Path

        from core.image_library import register_library

        register_library("pathways", Path(__file__).resolve().parent / "seed_data" / "images")
