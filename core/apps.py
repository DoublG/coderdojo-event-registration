from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from core.audit import register_models
        from core.uploads import connect_cleanup

        register_models()
        # Deletes replaced and orphaned uploads (CAPACITY.md, "Disk").
        connect_cleanup()
