from django.core.management.base import BaseCommand
from mailing.tasks import send_mail_to_all_users

class Command(BaseCommand):
    help = (
        "Test Mailing in background worker"
    )

    def handle(self, *args, **options):
        pass
        #send_mail_to_all_users.delay("some subject", "some message")

