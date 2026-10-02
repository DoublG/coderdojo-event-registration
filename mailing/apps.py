from django.apps import AppConfig


class MailingConfig(AppConfig):
    name = "mailing"

    def ready(self):
        from monitoring.collect import register_source

        from .queue_status import snapshot

        register_source("mail_queue", snapshot)  # /metrics/'s mail queue
