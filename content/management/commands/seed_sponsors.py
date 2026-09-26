from django.core.management.base import BaseCommand

from content.models import Sponsor
from core.audit import without_audit_log

# CoderDojo Belgium's sponsors and partners, as listed on coderdojobelgium.be
# (September 2026), in alphabetical order. No logos: upload them on the
# organisation dashboard's Sponsors page; until then the name is shown.
SPONSORS = [
    ("CBC", "https://www.cbc.be/particuliers/fr.html"),
    ("Cronos Groep", "https://cronos-groep.be/en/"),
    ("EVS", "https://evs.com/na"),
    ("EWI Vlaanderen", "https://www.ewi-vlaanderen.be/"),
    ("Flexmail", "https://flexmail.be/"),
    ("KBC", "https://www.kbc.be/particulieren/nl.html"),
    ("STEM-academie", "https://www.vlaio.be/nl/vlaio-netwerk/stemvlaio/stem-de-vrije-tijd/erkende-stem-academies-2024"),
    ("Telenet", "https://www.telenet.be"),
    ("Willow", "https://www.willow.co/"),
]


class Command(BaseCommand):
    help = "Seed the homepage's sponsors (\"Made possible by\"). Rerun-safe: only creates the ones that are missing."

    @without_audit_log
    def handle(self, *args, **options):
        created = 0
        for order, (name, url) in enumerate(SPONSORS, start=1):
            _, was_created = Sponsor.objects.get_or_create(name=name, defaults={"url": url, "order": order})
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"Done. created={created} sponsors."))
