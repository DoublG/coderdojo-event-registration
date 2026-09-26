from django.core.management.base import BaseCommand

from privacy.retention import apply_retention


class Command(BaseCommand):
    help = (
        "Run the nightly retention job now (privacy.retention): reminder mails and deletions for accounts "
        "unused for two years, old audit log entries, expired sessions. Safe to run twice."
    )

    def handle(self, *args, **options):
        done = apply_retention()
        self.stdout.write(", ".join(f"{name}: {count}" for name, count in done.items()))
