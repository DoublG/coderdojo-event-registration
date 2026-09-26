from django.core.management.base import BaseCommand

from privacy.erasure import replay_erasures


class Command(BaseCommand):
    help = (
        "After restoring a backup: erase again every account and child in the erasure log "
        "(privacy.ErasureRecord). Safe to run twice."
    )

    def handle(self, *args, **options):
        count = replay_erasures()
        self.stdout.write(self.style.SUCCESS(f"Erased again: {count}."))
