from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitoring"

    def ready(self):
        # Task timings and the workers' memory (monitoring.recorder).
        from . import celery_signals  # noqa: F401
