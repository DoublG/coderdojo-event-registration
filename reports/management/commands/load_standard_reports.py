from django.core.management.base import BaseCommand

from reports.standard_reports import install


class Command(BaseCommand):
    help = (
        "Install the standard reports (reports/standard_reports.py): create the missing ones and update the ones "
        "still exactly as installed. Never changes a report someone edited. Run on every deploy (scripts/deploy.sh)."
    )

    def handle(self, *args, **options):
        result = install()
        self.stdout.write(
            self.style.SUCCESS(f"Standard reports: {result['created']} created, {result['updated']} updated.")
        )
