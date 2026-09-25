from django.core.management.base import BaseCommand

from events.engagement import rebuild


class Command(BaseCommand):
    help = (
        "Recompute the engagement snapshot (events.NinjaEngagement) now instead of waiting for the "
        "nightly run. Safe to run any time: it replaces every row."
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Engagement snapshot: {rebuild()} rows."))
