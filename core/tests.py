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
        from content.models import Announcement, Promotion
        from dojos.testing import add_member, make_dojo
        from events.models import (
            Badge, Belt, Event, NinjaBadge, NinjaBelt, NinjaEngagement, NinjaEngagementChange, RegistrationCancellation,
            TeamAttendance,
        )
        from mailing.models import (
            ConsentEvent, EmailMessage, Journey, JourneyDelivery, MailPreference, Segment, SegmentGroup,
        )
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
            (RegistrationCancellation.objects.create(ninja=ninja, event=Event.objects.create(
                name="Gone", dojo=dojo, places=1, start_time=timezone.now(), end_time=timezone.now()),
                was_waitlisted=False), "Kid cancelled Gone"),
            (NinjaEngagementChange.objects.create(ninja=ninja, from_stage="regular", to_stage="at_risk",
                                                  changed_on=date(2026, 1, 1)), "Kid: regular"),
            (JourneyDelivery.objects.create(journey=Journey.objects.create(name="Hi", template_key="x"), user=user),
             "Hi → jan"),
            (NinjaEngagement.objects.create(ninja=ninja, dojo=dojo, stage="regular", computed_on=date(2026, 1, 1)),
             "Kid @ Ghent"),
            (EmailMessage.objects.create(user=user, category="service", subject="Hi", body=""), "jan — Hi"),
            (MailPreference.objects.create(user=user, category="newsletter", subscribed=True), "jan: newsletter on"),
            (ConsentEvent.objects.create(user=user, category="newsletter", subscribed=True, source="signup"), "jan: newsletter on"),
            (Promotion.objects.create(event=Event.objects.create(
                name="Coolest", dojo=dojo, places=1, start_time=timezone.now(), end_time=timezone.now()),
                placement=Promotion.HOMEPAGE_HERO), "Coolest (Homepage"),
            (TeamAttendance.objects.create(event=Event.objects.create(
                name="Run", dojo=dojo, places=1, start_time=timezone.now(), end_time=timezone.now()),
                membership=add_member(dojo, User.objects.create(username="piet")), attended=True), "piet at Run"),
        ]
        for row, expected in rows:
            model = type(row)
            with self.subTest(model=model.__name__):
                loaded = model.objects.get(pk=row.pk)
                with self.assertNumQueries(0):
                    self.assertIn(expected, str(loaded))


class AdminStaysFullyUsableTests(TestCase):
    """The Django admin is the emergency tool: whatever breaks must be
    fixable there, so nobody ever needs direct database access (CLAUDE.md).
    Every registered model lets a superuser add, change and delete, apart
    from the exceptions below, each with its reason."""

    # (app_label.ModelName, permission) -> why it's not needed.
    EXCEPTIONS = {
        ("applications.BackgroundCheck", "add"): "a review list over existing accounts; the accounts themselves "
                                                 "(check fields included) are fully editable in the User admin",
    }

    def test_superuser_can_add_change_and_delete_everything(self):
        from django.contrib import admin
        from django.test import RequestFactory

        from accounts.models import User

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create(username="root", is_staff=True, is_superuser=True)
        missing = []
        for model, model_admin in admin.site._registry.items():
            label = f"{model._meta.app_label}.{model.__name__}"
            for permission in ("add", "change", "delete"):
                if (label, permission) in self.EXCEPTIONS:
                    continue
                if not getattr(model_admin, f"has_{permission}_permission")(request):
                    missing.append(f"{label}: {permission}")
        self.assertEqual(missing, [], "the admin must stay fully usable for fixing things by hand")
