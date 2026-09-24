from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from dojos.testing import make_dojo

from .models import Announcement


class SeedAnnouncementsTests(TestCase):
    def test_seeds_dojos_without_updates_and_is_rerun_safe(self):
        dojos = [make_dojo(f"Dojo {n}") for n in range(8)]
        kept = dojos[0]
        Announcement.objects.create(dojo=kept, date="2026-01-01", text="Hand-written")

        call_command("seed_announcements", stdout=StringIO())
        count = Announcement.objects.count()
        call_command("seed_announcements", stdout=StringIO())

        self.assertGreater(count, 1)
        self.assertEqual(Announcement.objects.count(), count)
        self.assertEqual(list(kept.announcements.values_list("text", flat=True)), ["Hand-written"])
        self.assertFalse(Announcement.objects.filter(text__contains="{dojo}").exists())
