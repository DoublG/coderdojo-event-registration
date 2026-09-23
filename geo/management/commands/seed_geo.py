from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand

from geo.models import AdministrativeBoundary, Municipality

SEED_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "seed_data"
MUNICIPALITIES_FIXTURE = SEED_DATA_DIR / "municipalities.json"
BOUNDARIES_FIXTURE = SEED_DATA_DIR / "boundaries.json"


class Command(BaseCommand):
    help = (
        "Load municipalities and administrative boundaries from the bundled JSON "
        "dump (geo/seed_data/) instead of import_municipalities/import_boundaries, "
        "which need the Geo.be territorial-divisions geopackage on disk. Use this "
        "one for local dev/container seeding; re-run import_municipalities and "
        "import_boundaries + `manage.py dumpdata` to refresh the dump itself."
    )

    def handle(self, *args, **options):
        if Municipality.objects.exists() or AdministrativeBoundary.objects.exists():
            self.stdout.write("Municipality/AdministrativeBoundary data already present, skipping.")
            return

        call_command("loaddata", str(MUNICIPALITIES_FIXTURE))
        call_command("loaddata", str(BOUNDARIES_FIXTURE))

        self.stdout.write(self.style.SUCCESS(
            f"Done. municipalities={Municipality.objects.count()} "
            f"boundaries={AdministrativeBoundary.objects.count()}"
        ))
