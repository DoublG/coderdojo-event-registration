from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from dojos.models import Dojo
from geo.models import AdministrativeBoundary, Municipality

DOJOS_FIXTURE = Path(__file__).resolve().parent.parent.parent / "seed_data" / "dojos.json"


class Command(BaseCommand):
    help = (
        "Load dojos (name/address/geocoded location/municipality/province) from the "
        "bundled JSON dump (dojos/seed_data/dojos.json) instead of import_dojos, which "
        "scrapes the live CoderDojo Belgium site and geocodes every address against "
        "Nominatim. Use this one for local dev/container seeding; re-run import_dojos "
        "+ `manage.py dumpdata` to refresh the dump itself. Requires seed_geo (or the "
        "real import_municipalities/import_boundaries) to have run first."
    )

    def handle(self, *args, **options):
        if Dojo.objects.exists():
            self.stdout.write("Dojo data already present, skipping.")
            return

        if not Municipality.objects.exists() or not AdministrativeBoundary.objects.exists():
            raise CommandError(
                "No municipalities/boundaries found - run `manage.py seed_geo` "
                "(or the real import_municipalities/import_boundaries) first."
            )

        call_command("loaddata", str(DOJOS_FIXTURE))

        self.stdout.write(self.style.SUCCESS(f"Done. dojos={Dojo.objects.count()}"))
