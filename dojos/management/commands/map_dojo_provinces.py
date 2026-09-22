from django.contrib.gis.db.models.functions import Distance
from django.core.management.base import BaseCommand

from dojos.models import Dojo
from geo.models import AdministrativeBoundary


def find_province(location):
    province = AdministrativeBoundary.objects.filter(
        kind=AdministrativeBoundary.PROVINCE, boundary__contains=location
    ).first()
    if province:
        return province
    # Falls back to nearest province for points just outside every polygon
    # (e.g. a coastal/border dojo, or an edge simplified away by
    # import_boundaries' tolerance).
    return (
        AdministrativeBoundary.objects.filter(kind=AdministrativeBoundary.PROVINCE)
        .annotate(distance=Distance("boundary", location))
        .order_by("distance")
        .first()
    )


class Command(BaseCommand):
    help = "One-time backfill: set Dojo.province from Dojo.location for every dojo that has a location."

    def handle(self, *args, **options):
        mapped, skipped = 0, 0

        for dojo in Dojo.objects.exclude(location=None):
            province = find_province(dojo.location)
            if not province:
                self.stderr.write(self.style.WARNING(f"Skipping '{dojo.name}': no province found"))
                skipped += 1
                continue

            dojo.province = province
            dojo.save(update_fields=["province"])
            self.stdout.write(f"'{dojo.name}' -> {province.name}")
            mapped += 1

        self.stdout.write(self.style.SUCCESS(f"Done. mapped={mapped} skipped={skipped}"))
