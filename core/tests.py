from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from content.models import Testimonial
from core import image_library
from core.testing import TempMediaMixin
from dojos.models import Dojo
from pathways.models import Pathway


class HomeViewTests(TestCase):
    def setUp(self):
        # home() caches pathways/team/faqs (core/views.py) — the test DB
        # resets between tests, but the cache doesn't, so a stale hit from
        # an earlier test/run would otherwise leak in here.
        cache.clear()

    def test_empty_site_renders(self):
        """The homepage composes widgets from several apps — none of them
        should assume there's at least one row to work with."""
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")

    def test_populated_site_renders(self):
        Pathway.objects.create(name="Scratch")
        Dojo.objects.create(name="Ghent")
        Testimonial.objects.create(quote="Great!", author="A parent")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["pathways"]), 1)
        self.assertIsNotNone(response.context["testimonial"])


class ImageLibraryTests(TempMediaMixin, TestCase):
    def test_every_kind_has_images(self):
        for kind in image_library.LIBRARY_DIRS:
            self.assertTrue(any(image_library.LIBRARY_DIRS[kind].iterdir()), kind)

    def test_template_lists_match_their_folders(self):
        """Each template module lists exactly the files in its folder."""
        from accounts import template_avatars
        from dojos import template_icons
        from events import template_images

        for folder, templates in [
            (template_images.TEMPLATE_IMAGES_DIR, template_images.TEMPLATE_IMAGES),
            (template_icons.TEMPLATE_ICONS_DIR, template_icons.TEMPLATE_ICONS),
            (template_avatars.TEMPLATE_AVATARS_DIR, template_avatars.TEMPLATE_AVATARS),
            (template_avatars.TEMPLATE_KID_AVATARS_DIR, template_avatars.TEMPLATE_KID_AVATARS),
        ]:
            with self.subTest(folder=folder.name):
                self.assertEqual(
                    sorted(filename for filename, _label in templates),
                    sorted(path.name for path in folder.iterdir()),
                )

    def test_standard_image_is_stored_once_and_shared(self):
        first = Pathway.objects.create(name="Scratch")
        second = Pathway.objects.create(name="Scratch 2")
        image_library.use_library_image(first, "image", "pathways", "scratch.svg", save=True)
        image_library.use_library_image(second, "image", "pathways", "scratch.svg", save=True)

        second.refresh_from_db()
        self.assertEqual(second.image.name, "library/pathways/scratch.svg")
        self.assertEqual(second.image.url, "/media/library/pathways/scratch.svg")
        self.assertEqual(len(list((self.media_root / "library" / "pathways").iterdir())), 1)

    def test_rejects_names_outside_the_library(self):
        for bad in ["", "missing.svg", "../images/scratch.svg", "../../../website/settings.py"]:
            with self.assertRaises(ValueError):
                image_library.library_name("pathways", bad)

    def test_library_filename_only_matches_its_own_kind(self):
        pathway = Pathway(name="Scratch")
        image_library.use_library_image(pathway, "image", "pathways", "scratch.svg")
        self.assertEqual(image_library.library_filename(pathway.image, "pathways"), "scratch.svg")
        self.assertIsNone(image_library.library_filename(pathway.image, "events"))
        self.assertTrue(image_library.is_library_image(pathway.image))
        pathway.image = "pathways/uploaded.png"
        self.assertFalse(image_library.is_library_image(pathway.image))


class StrNeverQueriesTests(TestCase):
    """A __str__ that names a related object must not query: under ASGI a
    lazy lookup raises SynchronousOnlyOperation. Each model's default
    manager preloads what its __str__ reads (select_related)."""

    def test_every_str_is_query_free(self):
        from datetime import date

        from django.utils import timezone

        from accounts.models import Guardianship, Ninja, OrganisationRole, User
        from applications.models import Application, BackgroundCheckHistory
        from content.models import Announcement
        from dojos.testing import add_member, make_dojo
        from events.models import Badge, Belt, NinjaBadge, NinjaBelt
        from mailing.models import ConsentEvent, EmailMessage, MailPreference, Segment, SegmentGroup
        from notifications.models import Notification
        from pathways.models import PathwayProject, PathwayStep

        user = User.objects.create(username="jan")
        ninja = Ninja.objects.create(name="Kid")
        dojo = make_dojo("Ghent")
        pathway = Pathway.objects.create(name="Scratch")
        rows = [
            (Guardianship.objects.create(guardian=user, ninja=ninja), "jan → Kid"),
            (OrganisationRole.objects.create(account=user, role=OrganisationRole.BOARD), "jan ("),
            (Application.objects.create(account=user, kind=Application.MENTOR), "jan — "),
            (BackgroundCheckHistory.objects.create(account=user, decision="validated", reviewed_at=timezone.now()), "jan — "),
            (Announcement.objects.create(dojo=dojo, date=date(2026, 1, 1), text="Hi"), " - 2026-01-01"),
            (add_member(dojo, user), "(Mentor, Ghent)"),
            (NinjaBadge.objects.create(ninja=ninja, badge=Badge.objects.create(name="Star")), "Kid - Star"),
            (NinjaBelt.objects.create(ninja=ninja, belt=Belt.objects.create(level=1, name="White"), awarded_on=date(2026, 1, 1)), "Kid - White"),
            (Notification.objects.create(recipient=user, text="Hello"), "jan: Hello"),
            (PathwayStep.objects.create(pathway=pathway, title="Start"), "Scratch step 0: Start"),
            (PathwayProject.objects.create(pathway=pathway, title="Game"), "Scratch: Game"),
            (SegmentGroup.objects.create(segment=Segment.objects.create(name="Girlz")), "Girlz ("),
            (EmailMessage.objects.create(user=user, category="service", subject="Hi", body=""), "jan — Hi"),
            (MailPreference.objects.create(user=user, category="newsletter", subscribed=True), "jan: newsletter on"),
            (ConsentEvent.objects.create(user=user, category="newsletter", subscribed=True, source="signup"), "jan: newsletter on"),
        ]
        for row, expected in rows:
            model = type(row)
            with self.subTest(model=model.__name__):
                loaded = model.objects.get(pk=row.pk)
                with self.assertNumQueries(0):
                    self.assertIn(expected, str(loaded))
