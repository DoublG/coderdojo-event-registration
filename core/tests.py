from datetime import date

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from content.models import Testimonial
from core import image_library
from core.testing import TempMediaMixin
from dojos.models import Dojo
from dojos.testing import make_dojo
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
            Badge,
            Belt,
            Event,
            NinjaBadge,
            NinjaBelt,
            NinjaEngagement,
            NinjaEngagementChange,
            RegistrationCancellation,
            TeamAttendance,
        )
        from mailing.models import (
            ConsentEvent,
            EmailMessage,
            Journey,
            JourneyDelivery,
            MailPreference,
            Segment,
            SegmentGroup,
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
        from django.utils import translation

        for row, expected in rows:
            model = type(row)
            with self.subTest(model=model.__name__), translation.override("en-us"):
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


class TranslationTests(TestCase):
    """The site's texts come in Dutch and French (locale/, CLAUDE.md "i18n"):
    the pages families see follow the visitor's language."""

    def test_switcher_offers_english_dutch_and_french(self):
        response = self.client.get(reverse("home"))
        self.assertEqual([code for code, _name in response.context["AVAILABLE_LANGUAGES"]], ["en-us", "nl-be", "fr-be"])

    def test_pages_follow_the_browser_language(self):
        for language, heading in [("nl-be", "Bouw iets geweldigs met code."), ("fr-be", "Créez quelque chose de génial avec du code."),
                                  ("en-us", "Build something awesome with code.")]:
            response = self.client.get(reverse("home"), HTTP_ACCEPT_LANGUAGE=language)
            self.assertContains(response, heading)
            self.assertContains(response, f'<html lang="{language}"')

    def test_javascript_catalog_serves_bundle_texts(self):
        response = self.client.get(reverse("javascript-catalog"), HTTP_ACCEPT_LANGUAGE="nl-be")
        self.assertContains(response, "Zijbalk vastzetten")

    def test_dashboards_follow_the_language_too(self):
        from dojos.testing import make_champion, make_dojo

        champion = make_champion(username="champ")
        dojo = make_dojo("Ghent", champion=champion)
        self.client.force_login(champion)
        response = self.client.get(reverse("dojo_team_manage", kwargs={"dojo_id": dojo.id}), HTTP_ACCEPT_LANGUAGE="fr-be")
        self.assertContains(response, "Équipe actuelle")

    def test_python_texts_are_translated_too(self):
        from django.utils import translation

        from accounts.models import ninja_birth_date_error
        from mailing.categories import MailCategory

        with translation.override("nl-be"):
            self.assertEqual(str(MailCategory.REMINDER.label), "Herinneringen")
            self.assertIn("Ninja's zijn 7 tot 17 jaar oud", ninja_birth_date_error(date(2000, 1, 1)))
        with translation.override("fr-be"):
            self.assertEqual(str(MailCategory.REMINDER.label), "Rappels")



class ContentLanguagesTests(TestCase):
    """core.content_languages: the text in the asked language when the dojo
    wrote one, else the main language, flagged as a fallback."""

    def test_localized_and_fallback(self):
        from core.content_languages import normalize

        dojo = make_dojo("Brussels", languages=["nl-be", "fr-be"], description="Nederlands")
        dojo.set_translation("fr-be", "description", "Français")
        self.assertEqual((dojo.localized("description", "fr-be"), dojo.localized("description", "fr-be").is_fallback), ("Français", False))
        self.assertEqual((dojo.localized("description", "nl"), dojo.localized("description", "nl").is_fallback), ("Nederlands", False))
        english = dojo.localized("description", "en-us")
        self.assertEqual((english, english.is_fallback, english.language), ("Nederlands", True, "nl-be"))
        self.assertEqual(normalize("FR_be"), "fr-be")

    def test_clearing_a_translation_removes_it(self):
        dojo = make_dojo("Brussels", languages=["nl-be", "fr-be"])
        dojo.set_translation("fr-be", "tagline", "Salut")
        dojo.set_translation("fr-be", "tagline", "")
        self.assertEqual(dojo.translations, {})



class OrganisationContentLanguagesTests(TestCase):
    """The organisation's own content (settings.ORGANISATION_LANGUAGES, main
    first) gets a version per language, edited in the admin and on the
    Promotions page; dojo-scoped FAQs follow the dojo's languages."""

    def setUp(self):
        from accounts.models import User

        self.superuser = User.objects.create(username="root", is_staff=True, is_superuser=True)
        self.pathway = Pathway.objects.create(name="Web", subtitle="Build websites", description="HTML and CSS.")

    def test_pathway_page_uses_the_visitors_language(self):
        self.pathway.set_translation("nl-be", "name", "Websites")
        self.pathway.save()
        url = reverse("pathway_detail", kwargs={"pathway_id": self.pathway.id})
        self.assertContains(self.client.get(url, HTTP_ACCEPT_LANGUAGE="nl-be"), "Websites")
        self.assertContains(self.client.get(url, HTTP_ACCEPT_LANGUAGE="fr-be"), "Web")

    def test_admin_edits_translations_per_language(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:pathways_pathway_change", args=[self.pathway.id])
        page = self.client.get(url)
        self.assertContains(page, "tr__nl-be__name")
        self.assertContains(page, "tr__fr-be__description")
        self.assertNotContains(page, "tr__en-us__name")

        data = {"name": "Web", "subtitle": "Build websites", "description": "HTML and CSS.", "min_age": "", "max_age": "",
                "no_experience_needed": "on", "translations": "{}", "tr__nl-be__name": "Websites", "tr__fr-be__name": "Sites web"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.content[:3000])
        self.pathway.refresh_from_db()
        self.assertEqual(self.pathway.translations, {"nl-be": {"name": "Websites"}, "fr-be": {"name": "Sites web"}})

    def test_dojo_faq_follows_the_dojo_languages(self):
        from content.models import FAQ

        dojo = make_dojo("Ghent", languages=["nl-be"])
        self.assertEqual(FAQ(dojo=dojo, question="?", answer="!").content_languages(), ["nl-be"])
        self.assertEqual(FAQ(question="?", answer="!").content_languages(), ["en-us", "nl-be", "fr-be"])

    def test_untranslated_faq_answer_says_only_in_english(self):
        from content.models import FAQ

        FAQ.objects.create(question="Is it free?", answer="Yes, always.")
        cache.clear()  # the homepage caches its FAQs
        response = self.client.get(reverse("home"), HTTP_ACCEPT_LANGUAGE="nl-be")
        self.assertContains(response, "Yes, always.")
        self.assertContains(response, "Alleen in het English")



class SeedContentLanguagesTests(TestCase):
    """manage.py seed_content_languages: realistic languages per region and
    the seeded texts in them; rerun-safe."""

    def test_languages_by_region(self):
        from core.management.commands.seed_content_languages import seeded_languages
        from geo.models import AdministrativeBoundary

        def province(name):
            return AdministrativeBoundary.objects.create(
                name=name, kind=AdministrativeBoundary.PROVINCE,
                boundary=MultiPolygon(Polygon(((4, 50), (5, 50), (5, 51), (4, 50)))),
            )

        walloon, flemish = province("Province de Namur"), province("Provincie Limburg")
        for i in range(12):
            wallonia = seeded_languages(make_dojo(f"W{i}", province=walloon), km_from_brussels=60)
            self.assertEqual(wallonia[0], "fr-be")
            self.assertIn(wallonia, (["fr-be"], ["fr-be", "en-us"]))
            flanders = seeded_languages(make_dojo(f"F{i}", province=flemish), km_from_brussels=80)
            self.assertIn(flanders, (["nl-be"], ["nl-be", "en-us"], ["nl-be", "fr-be"]))
        near = seeded_languages(make_dojo("Near", province=flemish), km_from_brussels=8)
        self.assertEqual(near, ["nl-be", "fr-be", "en-us"])

    def test_texts_in_the_dojo_languages_and_rerun_safe(self):
        from io import StringIO

        from django.core.management import call_command

        from content.models import FAQ
        from events.management.commands.seed_events import description_for
        from events.models import Event

        dojo = make_dojo("Namur", languages=["fr-be", "en-us"], tagline="Seeing a kid's face light up when their code finally runs — that's the whole job.")
        faq = FAQ.objects.create(dojo=dojo, question="Is there parking nearby?", answer="Yes, free parking is available right outside the venue.")
        global_faq = FAQ.objects.create(question="Is it really free?", answer="Yes — every Dojo session is free, run entirely by volunteers.")
        event = Event.objects.create(dojo=dojo, name="Coding Saturday", description=description_for("Coding Saturday"),
                                     start_time=timezone.now(), end_time=timezone.now(), places=5)
        pathway = Pathway.objects.create(name="Web Development", subtitle="x")

        call_command("seed_content_languages", stdout=StringIO())
        for obj in (dojo, faq, global_faq, event, pathway):
            obj.refresh_from_db()
        self.assertTrue(dojo.tagline.startswith("Voir le visage"))
        self.assertTrue(dojo.translation_for("en-us", "tagline").startswith("Seeing a kid"))
        self.assertEqual(faq.question, "Y a-t-il un parking à proximité ?")
        self.assertEqual(faq.translation_for("nl-be", "question"), "")
        self.assertEqual(global_faq.question, "Is it really free?")
        self.assertEqual(global_faq.translation_for("nl-be", "question"), "Is het echt gratis?")
        self.assertEqual(event.name, "Samedi code")
        self.assertIn("**Samedi code**", event.description)
        self.assertEqual(pathway.translation_for("fr-be", "name"), "Développement web")

        out = StringIO()
        call_command("seed_content_languages", stdout=out)
        self.assertNotRegex(out.getvalue(), r"=[1-9]")



class ContactAndCodeOfConductTests(TestCase):
    """The footer's contact details (settings.ORGANISATION_CONTACT) and its
    Contact and Code of conduct pages."""

    def test_footer_shows_the_organisation_and_links_the_pages(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'href="mailto:info@coderdojobelgium.be"')
        self.assertContains(response, "Liersesteenweg 4, 2800 Mechelen")
        self.assertContains(response, f'href="{reverse("contact")}"')
        self.assertContains(response, f'href="{reverse("code_of_conduct")}"')

    def test_contact_page(self):
        response = self.client.get(reverse("contact"))
        self.assertContains(response, "0523.889.476")
        self.assertContains(response, "https://www.instagram.com/coderdojobelgium/")

    def test_code_of_conduct_in_the_visitors_language(self):
        self.assertContains(self.client.get(reverse("code_of_conduct")), "call 112")
        self.assertContains(self.client.get(reverse("code_of_conduct"), HTTP_ACCEPT_LANGUAGE="nl-be"), "Gedragscode")
