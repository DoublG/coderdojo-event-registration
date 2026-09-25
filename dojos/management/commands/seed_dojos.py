from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from dojos.languages import region_languages
from dojos.models import Dojo
from geo.models import AdministrativeBoundary, Municipality

DOJOS_FIXTURE = Path(__file__).resolve().parent.parent.parent / "seed_data" / "dojos.json"

# Statuses given to the last few dojos (by id), so the draft / dormant /
# archived states have something to show; all others are active. The
# later seeders give these no upcoming sessions (and a draft one no
# history), matching the lifecycle rules.
LIFECYCLE_EXAMPLES = [Dojo.DRAFT, Dojo.DORMANT, Dojo.ARCHIVED]


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
        # The fixture predates Dojo.status; these are real, running dojos —
        # except the last few, which exercise the lifecycle (DATA_MODEL.md §3).
        Dojo.objects.update(status=Dojo.ACTIVE)
        for dojo in Dojo.objects.select_related("province", "municipality"):
            dojo.languages = region_languages(dojo)
            dojo.save(update_fields=["languages"])
        lifecycle_examples = list(Dojo.objects.order_by("-id")[:len(LIFECYCLE_EXAMPLES)])
        for dojo, status in zip(lifecycle_examples, LIFECYCLE_EXAMPLES, strict=False):
            dojo.status = status
            dojo.save(update_fields=["status"])

        self.stdout.write(self.style.SUCCESS(
            f"Done. dojos={Dojo.objects.count()} "
            f"(non-active: {', '.join(f'{d.name}={d.status}' for d in lifecycle_examples)})"
        ))
