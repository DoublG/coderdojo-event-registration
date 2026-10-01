import re
from datetime import date

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from content.models import Testimonial
from core import image_library
from core.testing import TempMediaMixin
from dojos.models import Dojo
from dojos.testing import make_champion, make_dojo
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

        from accounts.models import AdminAccessGrant, Guardianship, Ninja, OrganisationRole, User
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
            DojoMailMute,
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
            (AdminAccessGrant.objects.create(account=user, reason="Fix", expires_at=timezone.now()), "jan ("),
            (Application.objects.create(account=user, kind=Application.MENTOR), "jan — "),
            (
                BackgroundCheckHistory.objects.create(account=user, decision="validated", reviewed_at=timezone.now()),
                "jan — ",
            ),
            (Announcement.objects.create(dojo=dojo, date=date(2026, 1, 1), text="Hi"), " - 2026-01-01"),
            (add_member(dojo, user), "(Mentor, Ghent)"),
            (NinjaBadge.objects.create(ninja=ninja, badge=Badge.objects.create(name="Star")), "Kid - Star"),
            (
                NinjaBelt.objects.create(
                    ninja=ninja, belt=Belt.objects.create(level=1, name="White"), awarded_on=date(2026, 1, 1)
                ),
                "Kid - White",
            ),
            (Notification.objects.create(recipient=user, text="Hello"), "jan: Hello"),
            (PathwayStep.objects.create(pathway=pathway, title="Start"), "Scratch step 0: Start"),
            (PathwayProject.objects.create(pathway=pathway, title="Game"), "Scratch: Game"),
            (SegmentGroup.objects.create(segment=Segment.objects.create(name="Girlz")), "Girlz ("),
            (
                RegistrationCancellation.objects.create(
                    ninja=ninja,
                    event=Event.objects.create(
                        name="Gone", dojo=dojo, places=1, start_time=timezone.now(), end_time=timezone.now()
                    ),
                    was_waitlisted=False,
                ),
                "Kid cancelled Gone",
            ),
            (
                NinjaEngagementChange.objects.create(
                    ninja=ninja, from_stage="regular", to_stage="at_risk", changed_on=date(2026, 1, 1)
                ),
                "Kid: regular",
            ),
            (
                JourneyDelivery.objects.create(journey=Journey.objects.create(name="Hi", template_key="x"), user=user),
                "Hi → jan",
            ),
            (
                NinjaEngagement.objects.create(ninja=ninja, dojo=dojo, stage="regular", computed_on=date(2026, 1, 1)),
                "Kid @ Ghent",
            ),
            (EmailMessage.objects.create(user=user, category="service", subject="Hi", body=""), "jan — Hi"),
            (MailPreference.objects.create(user=user, category="newsletter", subscribed=True), "jan: newsletter on"),
            (
                ConsentEvent.objects.create(user=user, category="newsletter", subscribed=True, source="signup"),
                "jan: newsletter on",
            ),
            (
                ConsentEvent.objects.create(
                    user=user, category="dojo_news", dojo=dojo, subscribed=False, source="preferences"
                ),
                "jan: dojo_news from Ghent",
            ),
            (DojoMailMute.objects.create(user=user, dojo=dojo), "jan: muted Ghent"),
            (
                Promotion.objects.create(
                    event=Event.objects.create(
                        name="Coolest", dojo=dojo, places=1, start_time=timezone.now(), end_time=timezone.now()
                    ),
                    placement=Promotion.HOMEPAGE_HERO,
                ),
                "Coolest (Homepage",
            ),
            (
                TeamAttendance.objects.create(
                    event=Event.objects.create(
                        name="Run", dojo=dojo, places=1, start_time=timezone.now(), end_time=timezone.now()
                    ),
                    membership=add_member(dojo, User.objects.create(username="piet")),
                    attended=True,
                ),
                "piet at Run",
            ),
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
        # The one exception to the rule (DATA_MODEL.md §14): a log anyone can
        # edit proves nothing. Entries are only removed by code (retention,
        # erasure) or manage.py auditlogflush.
        ("auditlog.LogEntry", "add"): "the audit log is read-only",
        ("auditlog.LogEntry", "change"): "the audit log is read-only",
        ("auditlog.LogEntry", "delete"): "the audit log is read-only",
        # django-oauth-toolkit's own admin (the API, DATA_MODEL.md §13), for
        # security: a token typed in by hand would be a secret in the clear,
        # and deleting a token row can leave a refresh token that mints new
        # ones. Tokens are ended with the admin's "Revoke" action (or by
        # revoking the client); the applications are fully editable.
        ("oauth2_provider.AccessToken", "add"): "tokens are only issued by the OAuth flow",
        ("oauth2_provider.AccessToken", "delete"): "ended with the Revoke action, never a raw delete",
        ("oauth2_provider.RefreshToken", "add"): "tokens are only issued by the OAuth flow",
        ("oauth2_provider.RefreshToken", "delete"): "ended with the Revoke action, never a raw delete",
        ("oauth2_provider.Grant", "add"): "authorization codes are only issued by the OAuth flow (grant not enabled)",
        ("oauth2_provider.IDToken", "add"): "ID tokens are only issued by the OAuth flow (not enabled)",
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

    def test_every_admin_page_opens(self):
        """Not only allowed: the list, add and change page of every registered
        model render for a superuser (a non-editable field in a fieldset, or a
        new object without its dojo, used to crash a page)."""
        from django.contrib import admin
        from django.test import RequestFactory

        from accounts.models import User
        from dojos.testing import make_dojo
        from events.models import Event

        root = User.objects.create(username="root", is_staff=True, is_superuser=True)
        User.objects.create(username="someone", email="someone@example.com")
        dojo = make_dojo("Ghent")
        Event.objects.create(
            name="Session", dojo=dojo, start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        self.client.force_login(root)
        request = RequestFactory().get("/admin/")
        request.user = root
        broken = []
        for model, model_admin in admin.site._registry.items():
            app, name = model._meta.app_label, model._meta.model_name
            urls = [reverse(f"admin:{app}_{name}_changelist")]
            if model_admin.has_add_permission(request):
                urls.append(reverse(f"admin:{app}_{name}_add"))
            # From the admin's own list (a proxy like Background checks filters it).
            obj = (
                model_admin.get_queryset(request).exclude(pk=root.pk).first()
                if model is User
                else model_admin.get_queryset(request).first()
            )
            if obj is not None:
                urls.append(reverse(f"admin:{app}_{name}_change", args=[obj.pk]))
            for url in urls:
                status = self.client.get(url).status_code
                if status != 200:
                    broken.append(f"{url}: {status}")
        self.assertEqual(broken, [])


class TranslationTests(TestCase):
    """The site's texts come in Dutch and French (locale/, CLAUDE.md "i18n"):
    the pages families see follow the visitor's language."""

    def test_switcher_offers_english_dutch_and_french(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(
            [code for code, _name in response.context["AVAILABLE_LANGUAGES"]], ["en-us", "nl-be", "fr-be"]
        )

    def test_pages_follow_the_browser_language(self):
        for language, heading in [
            ("nl-be", "Bouw iets geweldigs met code."),
            ("fr-be", "Créez quelque chose de génial avec du code."),
            ("en-us", "Build something awesome with code."),
        ]:
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
        response = self.client.get(
            reverse("dojo_team_manage", kwargs={"dojo_id": dojo.id}), HTTP_ACCEPT_LANGUAGE="fr-be"
        )
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
        self.assertEqual(
            (dojo.localized("description", "fr-be"), dojo.localized("description", "fr-be").is_fallback),
            ("Français", False),
        )
        self.assertEqual(
            (dojo.localized("description", "nl"), dojo.localized("description", "nl").is_fallback),
            ("Nederlands", False),
        )
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

        data = {
            "name": "Web",
            "subtitle": "Build websites",
            "description": "HTML and CSS.",
            "min_age": "",
            "max_age": "",
            "no_experience_needed": "on",
            "translations": "{}",
            "tr__nl-be__name": "Websites",
            "tr__fr-be__name": "Sites web",
        }
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
                name=name,
                kind=AdministrativeBoundary.PROVINCE,
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

        dojo = make_dojo(
            "Namur",
            languages=["fr-be", "en-us"],
            tagline="Seeing a kid's face light up when their code finally runs — that's the whole job.",
        )
        faq = FAQ.objects.create(
            dojo=dojo,
            question="Is there parking nearby?",
            answer="Yes, free parking is available right outside the venue.",
        )
        global_faq = FAQ.objects.create(
            question="Is it really free?", answer="Yes — every Dojo session is free, run entirely by volunteers."
        )
        event = Event.objects.create(
            dojo=dojo,
            name="Coding Saturday",
            description=description_for("Coding Saturday"),
            start_time=timezone.now(),
            end_time=timezone.now(),
            places=5,
        )
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


class HealthCheckTests(TestCase):
    """/health/ for uptime monitoring (core/health.py): 200 while the
    database, Redis and the mail workers are fine, 503 naming the failed check."""

    def test_healthy_site_answers_ok_to_anyone(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "ok", "checks": {"database": "ok", "redis": "ok", "mail_workers": "ok"}}
        )
        self.assertIn("no-cache", response["Cache-Control"])

    def test_redis_down_is_503(self):
        from unittest import mock

        with (
            mock.patch("core.health.get_redis_connection", side_effect=ConnectionError("down")),
            self.assertLogs("core.health", "ERROR"),
        ):
            response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["checks"]["redis"], "error")
        self.assertEqual(response.json()["checks"]["database"], "ok")

    def test_mail_waiting_too_long_means_the_workers_are_down(self):
        from datetime import timedelta

        from mailing.categories import MailCategory
        from mailing.models import EmailMessage

        mail = EmailMessage.objects.create(
            category=MailCategory.SERVICE,
            recipient="a@example.com",
            subject="Hi",
            body="…",
            send_after=timezone.now() - timedelta(minutes=10),
        )
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)

        mail.send_after = timezone.now() - timedelta(hours=1)
        mail.save()
        with self.assertLogs("core.health", "ERROR"):
            response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["mail_workers"], "error")

    def test_only_get(self):
        self.assertEqual(self.client.post(reverse("health")).status_code, 405)


class AuditLogCoverageTests(TestCase):
    """Every model is either recorded in the audit log
    (AUDITLOG_INCLUDE_TRACKING_MODELS, DATA_MODEL.md §14) or listed here with
    the reason it isn't, so a new model can't be forgotten."""

    NOT_RECORDED = {
        "admin.LogEntry": "Django's own admin history, itself a log",
        "auditlog.LogEntry": "the audit log itself",
        "auth.Permission": "Django's permission list, from migrations",
        "contenttypes.ContentType": "Django's list of models, from migrations",
        "sessions.Session": "logins, changed on every request",
        "monitoring.CapacitySample": "table sizes and counters, nothing about a person",
        "django_celery_beat.ClockedSchedule": "the background jobs' schedule, a technical setting",
        "django_celery_beat.CrontabSchedule": "the background jobs' schedule, a technical setting",
        "django_celery_beat.IntervalSchedule": "the background jobs' schedule, a technical setting",
        "django_celery_beat.SolarSchedule": "the background jobs' schedule, a technical setting",
        "django_celery_beat.PeriodicTask": "the background jobs' schedule; beat updates it on every run",
        "django_celery_beat.PeriodicTasks": "beat's change marker",
        "django_celery_results.ChordCounter": "task bookkeeping",
        "django_celery_results.GroupResult": "task results",
        "django_celery_results.TaskResult": "task results",
        "events.NinjaEngagement": "rebuilt by the site every night",
        "events.NinjaEngagementChange": "written by the nightly rebuild; itself a history",
        "events.RegistrationCancellation": "itself a log of cancellations",
        "geo.AdministrativeBoundary": "reference data, from seed files",
        "geo.Municipality": "reference data, from seed files",
        "mailing.BounceRecord": "written by the bounce processing; itself a log",
        "mailing.EmailMessage": "the mail queue, updated by the workers on every send",
        "mailing.DojoMailMute": "every mute and unmute is a ConsentEvent, which is recorded",
        "mailing.JourneyDelivery": "written by the journeys job; itself a log",
        "mailing.ProcessedImapMessage": "bounce-mailbox bookkeeping",
        "notifications.Notification": "written by the site; marking read is no change worth recording",
        "privacy.ErasureRecord": "itself the log of erasures, without personal data",
        "oauth2_provider.AccessToken": "API tokens, made every hour by the clients themselves",
        "oauth2_provider.RefreshToken": "API tokens (the client credentials grant gets none)",
        "oauth2_provider.Grant": "authorization codes (that grant isn't enabled)",
        "oauth2_provider.IDToken": "OpenID Connect tokens (not enabled)",
        "oauth2_provider.DeviceGrant": "device codes (that grant isn't enabled)",
        "privacy.RetentionNotice": "written by the retention job; itself a log of reminders",
        "otp_static.StaticToken": "backup codes: secrets, each deleted when it's used; the device row is recorded",
        # django-silk: development-only profiling, never installed in production.
        "silk.Request": "development-only profiling (django-silk), written on every request",
        "silk.Response": "development-only profiling (django-silk), written on every request",
        "silk.SQLQuery": "development-only profiling (django-silk), written on every query",
        "silk.Profile": "development-only profiling (django-silk)",
    }

    def test_every_model_is_recorded_or_has_a_reason(self):
        from auditlog.registry import auditlog
        from django.apps import apps

        undecided = sorted(
            model._meta.label
            for model in apps.get_models()
            if not model._meta.auto_created
            and not auditlog.contains(model)
            and model._meta.label not in self.NOT_RECORDED
        )
        self.assertEqual(undecided, [], "add it to AUDITLOG_INCLUDE_TRACKING_MODELS, or to NOT_RECORDED with a reason")
        # A development-only app (django-silk) isn't installed everywhere.
        installed = {model._meta.label: model for model in apps.get_models()}
        both = sorted(
            label for label in self.NOT_RECORDED if label in installed and auditlog.contains(installed[label])
        )
        self.assertEqual(both, [], "recorded, so remove it from NOT_RECORDED")


class AuditLogTests(TestCase):
    """What the audit log records (DATA_MODEL.md §14)."""

    def setUp(self):
        from accounts.models import Guardianship, Ninja, User

        self.parent = User.objects.create(username="an", email="an@example.com")
        self.child = Ninja.objects.create(name="Lotte", allergies_notes="Peanuts")
        Guardianship.objects.create(guardian=self.parent, ninja=self.child)

    def entries(self, obj):
        from auditlog.models import LogEntry

        return LogEntry.objects.get_for_object(obj).order_by("pk")

    def test_a_change_records_who_made_it_and_no_address(self):
        from auditlog.context import set_actor

        with set_actor(self.parent):
            self.child.name = "Lotte P."
            self.child.save()
        entry = self.entries(self.child).last()
        self.assertEqual(entry.actor, self.parent)
        self.assertEqual(entry.changes_dict["name"], ["Lotte", "Lotte P."])
        self.assertIsNone(entry.remote_addr)

    def test_a_request_records_the_account_but_no_address_or_port(self):
        from auditlog.models import LogEntry

        from mailing.models import MailPreference

        self.client.force_login(self.parent)
        self.client.post(
            reverse("mail_preferences"),
            {"category_newsletter": "on", "preferred_language": "en-us"},
            HTTP_X_FORWARDED_FOR="203.0.113.7",
            HTTP_X_FORWARDED_PORT="443",
        )
        preference = MailPreference.objects.get(user=self.parent, category="newsletter")
        entry = LogEntry.objects.get_for_object(preference).get()
        self.assertEqual(entry.actor, self.parent)
        self.assertIsNone(entry.remote_addr)
        self.assertIsNone(entry.remote_port)

    def test_health_notes_are_masked(self):
        self.child.allergies_notes = "Peanuts and milk"
        self.child.save()
        entry = self.entries(self.child).last()
        self.assertIn("allergies_notes", entry.changes_dict)
        self.assertNotIn("milk", str(entry.changes))
        self.assertNotIn("Peanuts", str(entry.changes))

    def test_passwords_are_masked_and_logins_not_recorded(self):
        from django.utils import timezone

        before = self.entries(self.parent).count()
        self.parent.last_login = timezone.now()
        self.parent.save()
        self.assertEqual(self.entries(self.parent).count(), before)
        self.parent.set_password("a new secret")
        self.parent.save()
        self.assertNotIn(self.parent.password, str(self.entries(self.parent).last().changes))

    def test_mark_all_present_is_recorded(self):
        from datetime import timedelta

        from django.utils import timezone

        from dojos.testing import make_champion, make_dojo
        from events.models import Event, Registration

        champion = make_champion(username="champ")
        dojo = make_dojo("Ghent", champion=champion)
        start = timezone.now()
        event = Event.objects.create(
            name="Coding",
            dojo=dojo,
            places=5,
            start_time=start,
            end_time=start + timedelta(hours=2),
            status=Event.OPEN,
        )
        registration = Registration.objects.create(event=event, ninja=self.child, waiting_list=False, position=1)
        self.client.force_login(champion)
        self.client.post(reverse("dojo_event_attendance_mark_all", args=[dojo.id, event.id]))
        registration.refresh_from_db()
        self.assertTrue(registration.attended)
        entry = self.entries(registration).last()
        self.assertEqual((entry.actor, entry.changes_dict["attended"]), (champion, ["None", "True"]))

    def test_seeding_is_not_recorded(self):
        from auditlog.models import LogEntry

        from core.audit import without_audit_log

        @without_audit_log
        def seed():
            from accounts.models import Ninja

            Ninja.objects.create(name="Seeded")

        before = LogEntry.objects.count()
        seed()
        self.assertEqual(LogEntry.objects.count(), before)


class AuditLogAccessTests(TestCase):
    """Views of special-category data are recorded (DATA_MODEL.md §14 phase 3)."""

    def setUp(self):
        from datetime import timedelta

        from accounts.models import Guardianship, Ninja, User
        from dojos.testing import add_member, make_champion, make_mentor
        from events.models import Event, Registration

        self.champion = make_champion(username="champ")
        self.dojo = make_dojo("Ghent", champion=self.champion)
        self.mentor = make_mentor(username="mentor")
        add_member(self.dojo, self.mentor)
        parent = User.objects.create(username="an")
        self.with_notes = Ninja.objects.create(name="Lotte", allergies_notes="Peanuts")
        self.without_notes = Ninja.objects.create(name="Mats")
        start = timezone.now() + timedelta(days=1)
        self.event = Event.objects.create(
            name="Coding",
            dojo=self.dojo,
            places=5,
            start_time=start,
            end_time=start + timedelta(hours=2),
            status=Event.OPEN,
        )
        for position, ninja in enumerate([self.with_notes, self.without_notes]):
            Guardianship.objects.create(guardian=parent, ninja=ninja)
            Registration.objects.create(event=self.event, ninja=ninja, waiting_list=False, position=position)

    def views(self, obj):
        from auditlog.models import LogEntry

        return list(LogEntry.objects.get_for_object(obj).filter(action=LogEntry.Action.ACCESS))

    def test_the_champion_seeing_health_notes_is_recorded(self):
        self.client.force_login(self.champion)
        url = reverse("dojo_event_attendance", args=[self.dojo.id, self.event.id])
        self.assertContains(self.client.get(url), "Peanuts")
        [entry] = self.views(self.with_notes)
        self.assertEqual(entry.actor, self.champion)
        self.assertEqual(self.views(self.without_notes), [])
        # The dashboard shows the same list, so it's recorded again.
        self.client.get(reverse("dojo_dashboard", args=[self.dojo.id]))
        self.assertEqual(len(self.views(self.with_notes)), 2)

    def test_a_mentor_sees_no_notes_so_nothing_is_recorded(self):
        self.client.force_login(self.mentor)
        url = reverse("dojo_event_attendance", args=[self.dojo.id, self.event.id])
        self.assertNotContains(self.client.get(url), "Peanuts")
        self.assertEqual(self.views(self.with_notes), [])

    def test_opening_a_child_in_the_django_admin_is_recorded(self):
        from accounts.models import User

        root = User.objects.create(username="root", is_staff=True, is_superuser=True)
        self.client.force_login(root)
        url = reverse("admin:accounts_ninja_change", args=[self.with_notes.id])
        self.assertEqual(self.client.get(url).status_code, 200)
        [entry] = self.views(self.with_notes)
        self.assertEqual(entry.actor, root)

    def test_the_organisation_export_is_recorded(self):
        from accounts.models import OrganisationRole, User

        admin = User.objects.create(username="orgadmin")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        parent = User.objects.get(username="an")
        self.client.force_login(admin)
        self.client.get(reverse("manage_privacy_export", args=[parent.id]))
        [entry] = self.views(parent)
        self.assertEqual(entry.actor, admin)


class AuditLogAdminTests(TestCase):
    """The audit log is shown only in the Django admin, read-only, to the
    organisation's admin role (DATA_MODEL.md §14 phase 4)."""

    def setUp(self):
        from accounts.models import OrganisationRole, User

        self.admin = User.objects.create(username="orgadmin")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.board = User.objects.create(username="board")
        OrganisationRole.objects.create(account=self.board, role=OrganisationRole.BOARD)
        self.dojo = make_dojo("Ghent")

    def test_the_admin_role_sees_the_audit_log(self):
        from core.testing import with_admin_access

        self.client.force_login(with_admin_access(self.admin))
        self.assertEqual(self.client.get(reverse("admin:auditlog_logentry_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:dojos_dojo_auditlog", args=[self.dojo.id])).status_code, 200)
        self.assertContains(
            self.client.get(reverse("admin:dojos_dojo_changelist")),
            reverse("admin:dojos_dojo_auditlog", args=[self.dojo.id]),
        )

    def test_the_board_does_not(self):
        from core.testing import with_admin_access

        self.client.force_login(with_admin_access(self.board))
        self.assertEqual(self.client.get(reverse("admin:auditlog_logentry_changelist")).status_code, 403)
        # The board may view dojos, but not their audit history.
        self.assertEqual(self.client.get(reverse("admin:dojos_dojo_auditlog", args=[self.dojo.id])).status_code, 403)
        response = self.client.get(reverse("admin:dojos_dojo_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("admin:dojos_dojo_auditlog", args=[self.dojo.id]))

    def test_nobody_can_edit_it_from_the_admin(self):
        from auditlog.models import LogEntry
        from django.contrib import admin
        from django.test import RequestFactory

        from accounts.models import User

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create(username="root", is_staff=True, is_superuser=True)
        model_admin = admin.site._registry[LogEntry]
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))


class SiteFormRenderingTests(TestCase):
    """Forms render through core/forms/field.html and form.html (core/forms.py,
    FORM_RENDERER): one layout for every field, the site's input classes."""

    def form(self, data=None):
        from django import forms

        class SampleForm(forms.Form):
            name = forms.CharField(label="Name", help_text="Your full name.")
            notes = forms.CharField(label="Notes", required=False, widget=forms.Textarea)
            kind = forms.ChoiceField(label="Kind", choices=[("a", "A"), ("b", "B")])
            size = forms.ChoiceField(label="Size", choices=[("s", "S"), ("l", "L")], widget=forms.RadioSelect)
            agree = forms.BooleanField(label="I agree", required=False)
            own = forms.CharField(label="Own", required=False, widget=forms.TextInput(attrs={"class": "mine"}))
            secret = forms.CharField(required=False, widget=forms.HiddenInput)

            def clean(self):
                raise forms.ValidationError("Something is off.")

        return SampleForm(data)

    def test_the_site_renderer_is_used(self):
        from django.conf import settings

        self.assertEqual(settings.FORM_RENDERER, "core.forms.SiteFormRenderer")

    def test_a_field_group(self):
        html = self.form()["name"].as_field_group()
        self.assertInHTML(
            '<label class="cd-form__label label" for="id_name">Name'
            '<span class="cd-form__required" aria-hidden="true">*</span></label>',
            html,
        )
        self.assertIn('class="cd-form__input body"', html)
        self.assertInHTML('<div class="cd-form__help caption" id="id_name_helptext">Your full name.</div>', html)
        self.assertNotIn("cd-form__errors", html)

    def test_input_classes_by_widget(self):
        form = self.form()
        self.assertIn('class="cd-form__textarea body"', str(form["notes"]))
        self.assertIn('class="cd-form__select body"', str(form["kind"]))
        self.assertIn('class="mine"', str(form["own"]))
        self.assertNotIn("cd-form__input", str(form["agree"]))

    def test_errors_come_under_the_input(self):
        html = self.form({"kind": "a", "size": "s"})["name"].as_field_group()
        self.assertLess(html.index("<input"), html.index('<ul class="cd-form__errors">'))
        self.assertIn('aria-invalid="true"', html)

    def test_checkbox_and_radio_layouts(self):
        form = self.form()
        self.assertIn('class="cd-form__checkbox-row"', form["agree"].as_field_group())
        radio = form["size"].as_field_group()
        self.assertIn('<fieldset class="cd-form__field cd-form__fieldset"', radio)
        self.assertIn("<legend", radio)

    def test_a_whole_form(self):
        html = str(self.form({"name": "Ann", "kind": "a", "size": "s"}))
        self.assertInHTML('<p class="cd-form__note cd-form__note--error caption">Something is off.</p>', html)
        self.assertIn('type="hidden" name="secret"', html)
        self.assertEqual(html.count('class="cd-form__field'), 6)

    def test_an_upload_with_a_current_file(self):
        from django import forms

        class UploadForm(forms.Form):
            file = forms.FileField(required=False)

        form = UploadForm(initial={"file": type("F", (), {"url": "/media/x.png", "__str__": lambda self: "x.png"})()})
        html = str(form["file"])
        self.assertIn('class="cd-file-input"', html)
        self.assertIn('class="cd-form__checkbox-row"', html)


class SiteFormTextsAreTranslatedTests(TestCase):
    """A form that renders through Django's form templates (core/forms.py)
    shows its fields' labels and help texts, so each must be a translated
    text: a model's own verbose_name/help_text is English-only (it's meant for
    the Django admin). Add every form that moves to {{ form }} or
    as_field_group here."""

    def forms(self):
        from accounts.forms import (
            AddChildForm,
            ChangeEmailForm,
            ChildAvatarForm,
            ChildLoginForm,
            ConfirmIdentityForm,
            EditAccountForm,
            EditChildForm,
            ForcedPasswordChangeForm,
            LoginForm,
            OrganisationEmailChangeForm,
            RegisterGuardianForm,
            SignUpChildForm,
            StyledPasswordResetForm,
            StyledSetPasswordForm,
        )
        from accounts.models import Ninja, User
        from accounts.two_step_forms import AppSetupForm
        from api.forms import ApiClientForm
        from applications.forms import BackgroundCheckUploadForm, ChampionApplicationForm, MentorApplicationForm
        from content.forms import PromotionForm, SponsorForm
        from dojos.forms import (
            AddMentorForm,
            AnnouncementForm,
            AwardBadgeForm,
            AwardBeltForm,
            DojoCreateForm,
            DojoProfileForm,
            PromoteYouthMentorForm,
            TransferChampionForm,
        )
        from dojos.testing import make_dojo
        from events.forms import BadgeForm, EventForm
        from events.models import Event, Registration
        from mailing.forms import (
            CampaignForm,
            DojoMailingForm,
            JourneyForm,
            NewTemplateForm,
            SegmentForm,
            TemplateVersionForm,
        )
        from privacy.forms import ConfirmUsernameForm

        user = User.objects.create(username="u")
        bruges = make_dojo("Bruges")
        return [
            SponsorForm(),
            PromotionForm(),
            BadgeForm(),
            DojoCreateForm(),
            AnnouncementForm(dojo=make_dojo("Ghent")),
            NewTemplateForm(),
            TemplateVersionForm(),
            BackgroundCheckUploadForm(),
            AppSetupForm(key="00" * 20, user=user),
            ConfirmIdentityForm(user),
            LoginForm(),
            StyledPasswordResetForm(),
            StyledSetPasswordForm(user),
            ForcedPasswordChangeForm(user),
            ChampionApplicationForm(account=user),
            MentorApplicationForm(account=user),
            RegisterGuardianForm(),
            DojoProfileForm(instance=make_dojo("Antwerp")),
            EventForm(dojo=bruges, instance=Event(dojo=bruges)),
            CampaignForm(),
            JourneyForm(),
            SegmentForm(),
            ConfirmUsernameForm(user),
            ChildLoginForm(Ninja(name="Emma")),
            AddMentorForm(),
            PromoteYouthMentorForm(candidates=Ninja.objects.none()),
            TransferChampionForm(candidates=bruges.memberships.all()),
            ApiClientForm(),
            AddChildForm(guardian=User(last_name="Peeters")),
            EditChildForm(instance=Ninja(name="Emma")),
            EditAccountForm(instance=user),
            ChangeEmailForm(user),
            ChildAvatarForm(Ninja(name="Emma")),
            OrganisationEmailChangeForm(user),
            SignUpChildForm(),
            AwardBeltForm(registration=Registration(pk=1, ninja=Ninja(name="Emma")), offered=[]),
            AwardBadgeForm(registration=Registration(pk=1, ninja=Ninja(name="Emma")), offered=[]),
            DojoMailingForm(dojo=make_dojo("Liège")),
        ]

    def test_labels_and_help_texts_are_translated(self):
        from django.utils.functional import Promise

        untranslated = [
            f"{type(form).__name__}.{name}.{attr}: {value!r}"
            for form in self.forms()
            for name, field in form.fields.items()
            for attr in ("label", "help_text")
            if (value := getattr(field, attr)) and not isinstance(value, Promise)
        ]
        self.assertEqual(untranslated, [])


class VendoredHtmxTests(TestCase):
    """htmx comes from our own static files (core/static/core/vendor/htmx/),
    never from a CDN: one connection less per page, and visitors' IP
    addresses don't go to a third party. Covers the three page shells."""

    SCRIPT_SRC = re.compile(r'<script[^>]*\ssrc="([^"]+)"')

    def script_sources(self, response):
        self.assertEqual(response.status_code, 200)
        return self.SCRIPT_SRC.findall(response.content.decode())

    def assert_scripts_are_ours(self, response, *expected):
        sources = self.script_sources(response)
        for src in sources:
            self.assertTrue(src.startswith("/"), f"{src} is loaded from another site")
            if src.startswith(settings.STATIC_URL):
                path = src.removeprefix(settings.STATIC_URL)
                self.assertIsNotNone(finders.find(path), f"{src} doesn't exist")
        for name in expected:
            self.assertTrue(any(src.endswith(name) for src in sources), f"{name} isn't loaded")

    def test_the_public_site(self):
        cache.clear()
        self.assert_scripts_are_ours(self.client.get(reverse("home")), "htmx-2.0.4.min.js")

    def test_the_dojo_admin_area(self):
        from dojos.testing import make_champion

        champion = make_champion(username="champ")
        dojo = make_dojo("Ghent", champion=champion)
        self.client.force_login(champion)
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))
        self.assert_scripts_are_ours(response, "htmx-2.0.4.min.js", "htmx-ext-ws-2.0.1.js")

    def test_the_organisation_dashboard(self):
        from accounts.models import OrganisationRole, User

        admin = User.objects.create(username="orgadmin")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        self.client.force_login(admin)
        response = self.client.get(reverse("manage_home"), follow=True)
        self.assertTemplateUsed(response, "core/_manage_base.html")
        self.assert_scripts_are_ours(response, "htmx-2.0.4.min.js")


class JavaScriptCatalogTests(TestCase):
    """The pages load bundle.js's texts from /jsi18n/<language>/<version>/,
    which browsers cache for a year (core.jsi18n)."""

    def test_the_page_links_the_catalog_for_its_language(self):
        from core.jsi18n import catalog_version

        cache.clear()
        response = self.client.get(reverse("home"), HTTP_ACCEPT_LANGUAGE="nl-be")
        self.assertContains(response, f'<script src="/jsi18n/nl-be/{catalog_version()}/"></script>', html=True)

    def test_the_language_comes_from_the_url_not_the_browser(self):
        url = reverse("javascript-catalog-versioned", kwargs={"language": "nl-be", "version": "any"})
        response = self.client.get(url, HTTP_ACCEPT_LANGUAGE="fr-be")
        self.assertContains(response, "Zijbalk vastzetten")
        self.assertIn("immutable", response["Cache-Control"])
        self.assertIn("max-age=31536000", response["Cache-Control"])

    def test_an_unknown_language_is_not_found(self):
        url = reverse("javascript-catalog-versioned", kwargs={"language": "de-de", "version": "any"})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_new_translations_get_a_new_version(self):
        """A compilemessages changes the URL, also on a running runserver."""
        import tempfile
        from pathlib import Path
        from unittest import mock

        from django.utils.autoreload import file_changed

        from core import jsi18n

        with tempfile.TemporaryDirectory() as folder:
            mo = Path(folder) / "djangojs.mo"
            mo.write_bytes(b"old")
            with mock.patch.object(jsi18n, "_catalog_files", return_value=[mo]):
                jsi18n.catalog_version.cache_clear()
                before = jsi18n.catalog_version()
                mo.write_bytes(b"new")
                self.assertEqual(jsi18n.catalog_version(), before)
                file_changed.send(sender=None, file_path=mo)
                self.assertNotEqual(jsi18n.catalog_version(), before)
        jsi18n.catalog_version.cache_clear()


class FontsTests(TestCase):
    """Nunito and Fredoka come from our own static files
    (core/static/core/fonts/), on every page shell."""

    def test_every_font_file_exists(self):
        css_path = finders.find("core/fonts/fonts.css")
        css = open(css_path).read()
        files = re.findall(r'url\("([^"]+)"\)', css)
        self.assertEqual(len(files), 4)
        for name in files:
            self.assertIsNotNone(finders.find(f"core/fonts/{name}"), f"{name} doesn't exist")
        for family in ("Nunito", "Fredoka"):
            self.assertIn(f'font-family: "{family}";', css)

    def assert_page_loads_the_fonts(self, response):
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(static("core/fonts/fonts.css"), html)
        preloads = re.findall(r'<link rel="preload" href="([^"]+)" as="font"', html)
        self.assertEqual(len(preloads), 2)
        for url in preloads:
            self.assertIsNotNone(finders.find(url.removeprefix(settings.STATIC_URL)), f"{url} doesn't exist")

    def test_the_public_site(self):
        cache.clear()
        self.assert_page_loads_the_fonts(self.client.get(reverse("home")))

    def test_the_dojo_admin_area(self):
        from dojos.testing import make_champion

        champion = make_champion(username="champ")
        dojo = make_dojo("Ghent", champion=champion)
        self.client.force_login(champion)
        self.assert_page_loads_the_fonts(self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id})))

    def test_the_organisation_dashboard(self):
        from accounts.models import OrganisationRole, User

        admin = User.objects.create(username="orgadmin")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        self.client.force_login(admin)
        self.assert_page_loads_the_fonts(self.client.get(reverse("manage_home"), follow=True))


class ManagementAreaTests(TestCase):
    """One management area for the organisation and its dojos (DATA_MODEL.md
    §20): one entry point (/manage/), one sidebar with a switcher between
    what the account can manage, and the organisation's events next to their
    promotions. Only the navigation is shared: the organisation's pages still
    need the admin role, a dojo (an organisation dojo too) a membership and a
    valid background check."""

    def setUp(self):
        from datetime import timedelta

        from accounts.models import OrganisationRole
        from dojos.testing import add_member, make_champion, make_mentor
        from events.models import Event

        self.OrganisationRole = OrganisationRole
        self.org_dojo = make_dojo(
            "CoderDojo Belgium", champion=make_champion(username="orgchamp"), kind=Dojo.ORGANISATION
        )
        self.ghent = make_dojo("Ghent", champion=make_champion(username="ghentchamp"))
        # An organisation admin with a valid check, mentor on the organisation dojo's team and at Ghent.
        self.staff = make_mentor(username="staff")
        OrganisationRole.objects.create(account=self.staff, role=OrganisationRole.ADMIN)
        add_member(self.org_dojo, self.staff)
        add_member(self.ghent, self.staff)
        start = timezone.now() + timedelta(days=14)
        self.event = Event.objects.create(
            name="CoderDojo Girlz",
            dojo=self.org_dojo,
            status=Event.OPEN,
            places=10,
            start_time=start,
            end_time=start + timedelta(hours=4),
        )

    def _admin_without_check(self):
        from accounts.models import User

        user = User.objects.create(username="nocheck", email="nocheck@example.com")
        self.OrganisationRole.objects.create(account=user, role=self.OrganisationRole.ADMIN)
        return user

    def _dashboard(self, dojo):
        return reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id})

    # the switcher

    def test_the_switcher_lists_the_organisation_its_events_and_the_dojos(self):
        self.client.force_login(self.staff)
        for url in (reverse("manage_campaign_list"), self._dashboard(self.ghent)):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "data-cd-adminnav-switcher")
                self.assertContains(response, f'href="{reverse("manage_home")}"')
                self.assertContains(response, "Organisation events")
                self.assertContains(response, "Your dojos")
                self.assertContains(response, self._dashboard(self.org_dojo))
                self.assertContains(response, self._dashboard(self.ghent))

    def test_a_mentor_never_sees_the_organisation(self):
        from dojos.testing import add_member, make_mentor

        mentor = make_mentor(username="mentor")
        add_member(self.ghent, mentor)
        self.client.force_login(mentor)
        response = self.client.get(self._dashboard(self.ghent))
        self.assertNotContains(response, "data-cd-adminnav-switcher")  # one dojo: nothing to switch to
        self.assertNotContains(response, f'href="{reverse("manage_home")}"')
        self.assertEqual(self.client.get(reverse("manage_campaign_list")).status_code, 404)

    def test_an_organisation_admin_without_a_background_check_sees_no_dojos(self):
        """Not everyone in the organisation needs a check: without one, the
        organisation's pages only, and a dojo is a 404, even on its team."""
        from dojos.testing import add_member

        admin = self._admin_without_check()
        add_member(self.org_dojo, admin)
        self.client.force_login(admin)
        response = self.client.get(reverse("manage_campaign_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-cd-adminnav-switcher")
        self.assertNotContains(response, "Organisation events")
        self.assertNotContains(response, self._dashboard(self.org_dojo))
        self.assertEqual(self.client.get(self._dashboard(self.org_dojo)).status_code, 404)

    def test_a_lapsed_check_takes_the_dojos_away_but_not_the_organisation(self):
        from datetime import timedelta

        self.staff.background_check_expires_at = timezone.now() - timedelta(days=1)
        self.staff.save(update_fields=["background_check_expires_at"])
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manage_campaign_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-cd-adminnav-switcher")
        self.assertNotContains(response, self._dashboard(self.ghent))

    def test_the_organisation_sidebar_links_its_events(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manage_campaign_list"))
        self.assertContains(response, f'href="{reverse("dojo_event_list", kwargs={"dojo_id": self.org_dojo.id})}"')

    # one entry point

    def test_manage_opens_the_organisation_else_the_first_dojo(self):
        from accounts.models import User

        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse("manage_home")), reverse("manage_campaign_list"))
        self.client.force_login(User.objects.get(username="ghentchamp"))
        self.assertRedirects(self.client.get(reverse("manage_home")), self._dashboard(self.ghent))

    def test_manage_is_a_404_for_anyone_else(self):
        from accounts.models import User

        self.client.force_login(User.objects.create(username="parent"))
        self.assertEqual(self.client.get(reverse("manage_home")).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("manage_home")).status_code, 302)  # to login

    def test_one_manage_link_and_login_goes_there(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("manage_home")}"', count=1)
        self.assertNotContains(response, 'href="/admin/"')
        self.assertRedirects(self.client.get(reverse("login")), reverse("manage_home"), target_status_code=302)

    def test_an_organisation_admin_without_a_dojo_lands_in_the_organisation(self):
        self.client.force_login(self._admin_without_check())
        self.assertRedirects(self.client.get(reverse("login")), reverse("manage_home"), target_status_code=302)

    # promotions next to the event

    def _event_page(self):
        return reverse("dojo_event_detail", kwargs={"dojo_id": self.org_dojo.id, "event_id": self.event.id})

    def test_the_event_page_shows_its_promotions_to_an_organisation_admin(self):
        from content.models import Promotion

        promotion = Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO)
        self.client.force_login(self.staff)
        response = self.client.get(self._event_page())
        self.assertContains(response, "Promote this event")
        self.assertContains(response, f"{reverse('manage_promotion_create')}?event={self.event.id}")
        self.assertContains(response, reverse("manage_promotion_detail", kwargs={"promotion_id": promotion.id}))
        self.assertContains(response, "Showing")

    def test_the_team_without_the_organisation_role_sees_no_promotions(self):
        from accounts.models import User

        self.client.force_login(User.objects.get(username="orgchamp"))
        response = self.client.get(self._event_page())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Promote this event")
        self.assertNotContains(response, 'class="cd-card event-promotions-card"')

    def test_an_ended_event_can_no_longer_be_promoted(self):
        from datetime import timedelta

        self.event.start_time = timezone.now() - timedelta(days=2)
        self.event.end_time = self.event.start_time + timedelta(hours=4)
        self.event.save()
        self.client.force_login(self.staff)
        response = self.client.get(self._event_page())
        self.assertContains(response, 'class="cd-card event-promotions-card"')
        self.assertNotContains(response, "Promote this event")

    def test_promote_this_event_fills_in_the_event(self):
        self.client.force_login(self.staff)
        response = self.client.get(f"{reverse('manage_promotion_create')}?event={self.event.id}")
        self.assertEqual(str(response.context["form"]["event"].value()), str(self.event.id))

    def test_the_promotions_list_links_events_the_account_manages(self):
        from content.models import Promotion
        from events.models import Event

        other = make_dojo("Antwerp")
        other_event = Event.objects.create(
            name="Other",
            dojo=other,
            status=Event.OPEN,
            places=5,
            start_time=self.event.start_time,
            end_time=self.event.end_time,
        )
        Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO)
        Promotion.objects.create(event=other_event, placement=Promotion.EVENT_LIST_TOP)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manage_promotion_list"))
        self.assertContains(response, self._event_page())
        self.assertNotContains(
            response, reverse("dojo_event_detail", kwargs={"dojo_id": other.id, "event_id": other_event.id})
        )
        self.assertNotContains(response, "you need a valid background check")

    def test_the_promotions_list_says_how_to_plan_organisation_events(self):
        self.client.force_login(self._admin_without_check())
        self.assertContains(self.client.get(reverse("manage_promotion_list")), "you need a valid background check")


class OrganisationAreaTests(TestCase):
    """The organisation dashboard's areas (DATA_MODEL.md §23): each group of
    its sidebar is a permission (accounts.organisation.AREA_PERMISSIONS),
    held through the role groups or granted by hand, and checked by every
    page (require_area), the sidebar and /manage/'s landing."""

    def setUp(self):
        from core.manage import AREA_LANDINGS

        self.landings = {area: reverse(name) for area, name in AREA_LANDINGS.items()}

    def _account(self, username, *areas, role=None, **fields):
        from django.contrib.auth.models import Permission

        from accounts.models import OrganisationRole, User
        from accounts.organisation import AREA_PERMISSIONS

        user = User.objects.create(username=username, email=f"{username}@example.com", **fields)
        for area in areas:
            app_label, codename = AREA_PERMISSIONS[area].split(".")
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
        if role:
            OrganisationRole.objects.create(account=user, role=role)
        return User.objects.get(pk=user.pk)  # a fresh permission cache

    def test_each_role_opens_its_areas(self):
        from accounts.models import OrganisationRole
        from accounts.organisation import Area, areas_of

        admin = self._account("admin", role=OrganisationRole.ADMIN)
        reviewer = self._account("reviewer", role=OrganisationRole.REVIEWER)
        board = self._account("board", role=OrganisationRole.BOARD)
        self.assertEqual(
            areas_of(admin),
            [
                Area.COMMUNICATION,
                Area.PUBLIC_SITE,
                Area.NINJAS,
                Area.PRIVACY,
                Area.SECURITY,
                Area.PEOPLE,
                Area.AUDIT_LOG,
            ],
        )
        self.assertEqual(areas_of(reviewer), [Area.VOLUNTEERS])
        self.assertEqual(areas_of(board), [])

    def test_each_page_needs_its_own_area(self):
        for area, url in self.landings.items():
            with self.subTest(area=area):
                self.client.force_login(self._account(f"only-{area}", area))
                self.assertEqual(self.client.get(url).status_code, 200)
                for other, other_url in self.landings.items():
                    if other != area:
                        self.assertEqual(self.client.get(other_url).status_code, 404, other)

    def test_manage_opens_the_first_area_the_account_has(self):
        from accounts.organisation import Area

        for areas, landing in (
            ((Area.SECURITY,), Area.SECURITY),
            ((Area.PRIVACY, Area.NINJAS), Area.NINJAS),
            ((Area.VOLUNTEERS, Area.COMMUNICATION), Area.COMMUNICATION),
        ):
            with self.subTest(areas=areas):
                self.client.force_login(self._account("-".join(areas), *areas))
                self.assertRedirects(
                    self.client.get(reverse("manage_home")), self.landings[landing], fetch_redirect_response=False
                )

    def test_a_role_without_an_area_only_gets_the_django_admin_page(self):
        """The board has no area yet: /manage/ opens its page to ask for the
        Django admin (DATA_MODEL.md §23), and every area is a 404."""
        from accounts.models import OrganisationRole

        self.client.force_login(self._account("board", role=OrganisationRole.BOARD))
        self.assertRedirects(
            self.client.get(reverse("manage_home")), reverse("manage_admin_access"), fetch_redirect_response=False
        )
        self.assertEqual(self.client.get(reverse("manage_admin_access")).status_code, 200)
        for url in self.landings.values():
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_the_sidebar_shows_only_the_groups_of_its_areas(self):
        from accounts.organisation import Area

        self.client.force_login(self._account("privacy", Area.PRIVACY))
        response = self.client.get(self.landings[Area.PRIVACY])
        self.assertContains(response, "Accounts")
        self.assertContains(response, f'href="{self.landings[Area.PRIVACY]}"')
        for area in (Area.COMMUNICATION, Area.VOLUNTEERS, Area.PUBLIC_SITE, Area.NINJAS, Area.SECURITY):
            self.assertNotContains(response, f'href="{self.landings[area]}"')
        self.assertNotContains(response, reverse("manage_campaign_create"))

    def test_a_superuser_opens_every_area(self):
        root = self._account("root", is_superuser=True, is_staff=True)
        self.client.force_login(root)
        for url in self.landings.values():
            self.assertEqual(self.client.get(url).status_code, 200, url)


class ProfilingTests(TestCase):
    """core.profiling.profile: django-silk's silk_profile while silk is on
    (settings.SILK_ENABLED, development only), otherwise nothing at all, so
    code can be annotated without importing silk (not installed in
    production)."""

    def test_without_silk_it_changes_nothing(self):
        from django.test import override_settings

        from core.profiling import profile

        def view():
            return "page"

        with override_settings(SILK_ENABLED=False):
            self.assertIs(profile()(view), view)
            with profile(name="a block"):
                result = view()
        self.assertEqual(result, "page")

    def test_with_silk_it_is_silks_profiler(self):
        from django.apps import apps

        if not apps.is_installed("silk"):
            self.skipTest("django-silk isn't on in this run (settings.SILK_ENABLED)")
        from silk.profiling.profiler import silk_profile

        from core.profiling import profile

        self.assertIsInstance(profile(name="home"), silk_profile)


class AuditLogPageTests(TestCase):
    """The audit log on the organisation dashboard (/manage/audit-log/,
    core.audit_views, DATA_MODEL.md §14): read-only, for the organisation's
    admin role, with health, criminal-record and security values hidden."""

    def setUp(self):
        from accounts.models import OrganisationRole, User

        self.admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.url = reverse("manage_audit_log")
        self.client.force_login(self.admin)

    def _ninja(self, **fields):
        from accounts.models import Ninja

        return Ninja.objects.create(name="Lotte", family_name="Peeters", **fields)

    def test_only_the_admin_role_gets_in(self):
        from accounts.models import OrganisationRole, User

        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)  # to login
        for role in (OrganisationRole.BOARD, OrganisationRole.REVIEWER):
            other = User.objects.create(username=role, email=f"{role}@example.com")
            OrganisationRole.objects.create(account=other, role=role)
            self.client.force_login(other)
            self.assertEqual(self.client.get(self.url).status_code, 404, role)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/manage_audit_log.html")
        self.assertContains(response, f'href="{self.url}"')  # the sidebar link

    def test_it_is_read_only(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_ordinary_changes_are_shown(self):
        ninja = self._ninja()
        ninja.name = "Lotte-Marie"
        ninja.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Lotte-Marie")
        self.assertContains(response, "Lotte</span> → <span>Lotte-Marie")

    def test_health_criminal_and_security_values_are_hidden(self):
        from accounts.models import User

        ninja = self._ninja(allergies_notes="Peanut allergy")
        ninja.allergies_notes = "Peanut and egg allergy"
        ninja.save()
        volunteer = User.objects.create(username="vol", email="vol@example.com")
        volunteer.background_check_status = User.CHECK_REJECTED
        volunteer.set_password("s3cret-Password")
        volunteer.save()

        response = self.client.get(self.url)
        content = response.content.decode()
        for value in ("Peanut", "rejected", "Rejected", "pbkdf2", "s3cret"):
            self.assertNotIn(value, content)
        self.assertIn("****", content)
        by_field = {
            change["field"].lower(): change for _, _, changes in response.context["rows"] for change in changes
        }
        for field in ("allergies notes", "background check status", "password"):
            self.assertTrue(by_field[field.lower()]["hidden"], field)
        self.assertFalse(by_field["email address"]["hidden"])

    def test_a_field_without_a_privacy_decision_is_hidden(self):
        from accounts.models import Ninja

        from .audit import is_hidden

        self.assertTrue(is_hidden(Ninja, "no_such_field"))
        self.assertTrue(is_hidden(None, "name"))
        self.assertFalse(is_hidden(Ninja, "name"))
        self.assertTrue(is_hidden(Ninja, "allergies_notes"))
        # Who did something stays visible, though it's kept out of an export.
        from accounts.models import AdminAccessGrant

        self.assertFalse(is_hidden(AdminAccessGrant, "ended_by"))

    def test_filters(self):
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        from accounts.models import Ninja

        ninja = self._ninja()
        make_dojo("Dojo Gent")
        ninja.delete()

        response = self.client.get(self.url, {"q": "Gent"})
        found = [entry.object_repr for entry, _, _ in response.context["rows"]]
        self.assertTrue(found)
        self.assertTrue(all("Gent" in repr_ for repr_ in found), found)
        response = self.client.get(self.url, {"action": LogEntry.Action.DELETE})
        self.assertEqual([entry.action for entry, _, _ in response.context["rows"]], [LogEntry.Action.DELETE])
        response = self.client.get(self.url, {"type": ContentType.objects.get_for_model(Ninja).pk})
        self.assertTrue(response.context["rows"])
        self.assertTrue(all(entry.content_type.model == "ninja" for entry, _, _ in response.context["rows"]))
        # Nonsense filters are ignored, not errors.
        self.assertEqual(self.client.get(self.url, {"action": "x", "type": "999999", "page": "abc"}).status_code, 200)

    def test_pages(self):
        from auditlog.models import LogEntry

        from . import audit_views

        for _number in range(audit_views.PAGE_SIZE + 5):
            self._ninja()
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["rows"]), audit_views.PAGE_SIZE)
        self.assertContains(response, "page=2")
        on_page_two = LogEntry.objects.count() - audit_views.PAGE_SIZE
        self.assertEqual(
            len(self.client.get(self.url, {"page": 2}).context["rows"]), min(on_page_two, audit_views.PAGE_SIZE)
        )


class MarkdownifyTests(TestCase):
    """A team's Markdown (dojo and session pages) only becomes basic formatting."""

    def render(self, text):
        from core.templatetags.markdown_extras import markdownify

        return markdownify(text)

    def test_headings_start_at_h2(self):
        html = self.render("# Title\n\n## Part\n\n### Detail")
        self.assertIn("<h2>Title</h2>", html)
        self.assertIn("<h3>Part</h3>", html)
        self.assertIn("<h4>Detail</h4>", html)
        self.assertNotIn("<h1", html)

    def test_basic_formatting_stays(self):
        html = self.render("**bold** and *italic*\n\n- one\n- two\n\nSteps:\n\n1. first\n2. second")
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<em>italic</em>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<li>one</li>", html)
        self.assertIn("<ol>", html)

    def test_web_mail_and_relative_links_stay(self):
        html = self.render("[site](https://coderdojobelgium.be) [mail](mailto:info@example.org) [dojo](/dojos/1/)")
        self.assertIn('href="https://coderdojobelgium.be"', html)
        self.assertIn('href="mailto:info@example.org"', html)
        self.assertIn('href="/dojos/1/"', html)
        self.assertIn('rel="nofollow noopener noreferrer"', html)

    def test_script_links_lose_their_target(self):
        html = self.render("[a](javascript:alert(1)) [b](JaVaScRiPt:alert(1)) [c](data:text/html,x) [d](vbscript:x)")
        self.assertNotIn("href", html)
        self.assertNotIn("javascript", html.lower())
        self.assertNotIn("data:", html)

    def test_typed_html_shows_as_text(self):
        html = self.render('<div onclick="x()">hi</div><script>alert(1)</script>')
        self.assertNotIn("<div", html)
        self.assertNotIn("<script", html)
        self.assertIn("&lt;script&gt;", html)

    def test_images_code_and_quotes_are_not_allowed(self):
        html = self.render("![pixel](https://tracker.example/p.png)\n\n`code`\n\n    indented\n\n---")
        for tag in ("<img", "<code", "<pre", "<hr"):
            self.assertNotIn(tag, html)
        self.assertNotIn("tracker.example", html)
        self.assertIn("code", html)

    def test_empty_text_is_empty(self):
        self.assertEqual(self.render(""), "")
        self.assertEqual(self.render(None), "")


class SecurityHeadersTests(TestCase):
    """HTTPS, Content-Security-Policy and Permissions-Policy (settings.py, MAINTENANCE.md's security log)."""

    INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*type=\"application/json\")([^>]*)>")

    def get(self, url):
        return self.client.get(url, secure=True, HTTP_HOST="coolregistration.localhost")

    def nonce(self, response):
        match = re.search(r"'nonce-([^']+)'", response.headers.get("Content-Security-Policy", ""))
        self.assertIsNotNone(match, "no nonce in the Content-Security-Policy")
        return match.group(1)

    def test_every_page_gets_a_strict_script_policy(self):
        policy = self.get(reverse("home")).headers["Content-Security-Policy"]
        directives = dict(part.strip().split(" ", 1) for part in policy.split(";") if part.strip())
        self.assertIn("'nonce-", directives["script-src"])
        self.assertNotIn("unsafe-inline", directives["script-src"])
        self.assertNotIn("unsafe-eval", directives["script-src"])
        self.assertEqual(directives["object-src"], "'none'")
        self.assertEqual(directives["frame-ancestors"], "'none'")
        self.assertEqual(directives["form-action"], "'self'")

    def test_inline_scripts_carry_the_pages_nonce(self):
        champion = make_champion(username="csp-champion")
        dojo = make_dojo("CSP Dojo", champion=champion)
        public = [reverse("home"), reverse("dojo_list"), reverse("dojo_detail", args=[dojo.id]), reverse("login")]
        for url in public:
            self.assert_scripts_have_nonce(url)
        self.client.force_login(champion)
        for url in (
            reverse("account_home"),
            reverse("dojo_dashboard", args=[dojo.id]),
            reverse("dojo_manage", args=[dojo.id]),
        ):
            self.assert_scripts_have_nonce(url)

    def assert_scripts_have_nonce(self, url):
        response = self.get(url)
        self.assertEqual(response.status_code, 200, url)
        nonce = self.nonce(response)
        scripts = self.INLINE_SCRIPT.findall(response.content.decode())
        for attributes in scripts:
            self.assertIn(f'nonce="{nonce}"', attributes, f"an inline script without the nonce on {url}")

    def test_no_template_uses_inline_handlers_or_hx_on(self):
        """The policy blocks them: use data-confirm, data-autosubmit or data-action (bundle.js)."""
        from pathlib import Path

        handler = re.compile(r"\son[a-z]+\s*=\s*[\"']|\shx-on[:-]")
        found = []
        for path in Path(settings.BASE_DIR).glob("*/templates/**/*.html"):
            text = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|\{#.*?#\}", "", path.read_text(), flags=re.S)
            if handler.search(text):
                found.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(found, [])

    def test_permissions_policy_switches_off_unused_features(self):
        header = self.get(reverse("home")).headers["Permissions-Policy"]
        for feature in ("camera=()", "microphone=()", "payment=()", "usb=()"):
            self.assertIn(feature, header)
        for feature in (
            "geolocation=(self)",
            "publickey-credentials-get=(self)",
            "publickey-credentials-create=(self)",
        ):
            self.assertIn(feature, header)

    def test_https_settings(self):
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_the_proxy_header_makes_a_request_secure(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/", HTTP_X_FORWARDED_PROTO="https")
        self.assertTrue(request.is_secure())
        self.assertFalse(RequestFactory().get("/").is_secure())

    def test_oauth_follows_rfc_9700(self):
        oauth = settings.OAUTH2_PROVIDER
        for flag in (
            "COMPLIANT_BCP_RFC9700_IMPLICIT_GRANT",
            "COMPLIANT_BCP_RFC9700_PASSWORD_GRANT",
            "COMPLIANT_BCP_RFC9700_ACCESS_TOKEN_TRANSPORT",
            "COMPLIANT_BCP_RFC9700_TOKEN_STORAGE",
            "REFRESH_TOKEN_REUSE_PROTECTION",
        ):
            self.assertIs(oauth[flag], True, flag)
        self.assertEqual(oauth["ALLOWED_REDIRECT_URI_SCHEMES"], ["https"])

    def test_htmx_requests_in_the_management_area_send_the_csrf_token(self):
        """The bell's "Mark all as read" can arrive over the WebSocket, rendered without a token of its own."""
        champion = make_champion(username="csp-bell")
        dojo = make_dojo("Bell Dojo", champion=champion)
        self.client.force_login(champion)
        html = self.get(reverse("dojo_dashboard", args=[dojo.id])).content.decode()
        self.assertRegex(html, r"<body hx-headers='\{\"X-CSRFToken\": \"[^\"]+\"\}'>")


class AdminLoginWithoutAccessTests(TestCase):
    """A logged-in account without an open admin grant used to loop between the
    admin's login and the site's (which sends a logged-in account on to `next`)."""

    def setUp(self):
        from accounts.models import OrganisationRole, User

        self.admin = User.objects.create(username="orgadmin-noaccess")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.parent = User.objects.create(username="parent-noaccess")

    def admin_login(self):
        url = reverse("admin:index")
        return self.client.get(reverse("admin:login") + f"?next={url}")

    def test_an_organisation_role_is_sent_to_ask_for_access(self):
        self.client.force_login(self.admin)
        self.assertRedirects(
            self.client.get(reverse("admin:index")),
            reverse("admin:login") + "?next=/admin/",
            fetch_redirect_response=False,
        )
        self.assertRedirects(self.admin_login(), reverse("manage_admin_access"), fetch_redirect_response=False)

    def test_an_account_without_a_role_is_refused(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.admin_login().status_code, 403)

    def test_someone_not_logged_in_goes_to_the_sites_login(self):
        response = self.admin_login()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_with_an_open_grant_the_admin_opens(self):
        from core.testing import with_admin_access

        self.client.force_login(with_admin_access(self.admin))
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)


class UploadGuardrailTests(TempMediaMixin, TestCase):
    """core.uploads: uploaded images are checked, shrunk and re-encoded
    without their metadata, and deleted when nothing uses them any more;
    the background-check document is checked (CAPACITY.md, "Disk")."""

    @staticmethod
    def jpeg(size=(3000, 2000), orientation=None, gps=False):
        import io

        from PIL import Image

        image = Image.new("RGB", size, (200, 30, 30))
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # Make
        if orientation:
            exif[0x0112] = orientation
        if gps:
            exif[0x8825] = {1: "N", 2: (50.0, 51.0, 0.0)}
        out = io.BytesIO()
        image.save(out, "JPEG", exif=exif)
        return out.getvalue()

    @staticmethod
    def png(size=(300, 300), alpha=True):
        import io

        from PIL import Image

        out = io.BytesIO()
        Image.new("RGBA" if alpha else "RGB", size, (0, 0, 255, 128) if alpha else (0, 0, 255)).save(out, "PNG")
        return out.getvalue()

    def upload(self, name, data, content_type="image/jpeg"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(name, data, content_type=content_type)

    def stored(self, fieldfile):
        from PIL import Image

        fieldfile.open("rb")
        try:
            with Image.open(fieldfile) as image:
                image.load()
                return image.format, image.size, image.mode, image.getexif()
        finally:
            fieldfile.close()

    def test_an_uploaded_photo_is_shrunk_turned_upright_and_loses_its_metadata(self):
        dojo = make_dojo("Ghent")
        dojo.icon = self.upload("phone.JPEG", self.jpeg(orientation=6, gps=True))
        dojo.save()
        dojo.refresh_from_db()
        self.assertTrue(dojo.icon.name.startswith("dojos/phone") and dojo.icon.name.endswith(".jpg"))
        image_format, size, _, exif = self.stored(dojo.icon)
        self.assertEqual(image_format, "JPEG")
        # Orientation 6 is a quarter turn: the landscape photo becomes portrait, at most 512 px.
        self.assertEqual(size, (341, 512))
        self.assertEqual(dict(exif), {})

    def test_no_metadata_of_any_kind_survives(self):
        """Not only EXIF: XMP, comments, text chunks and colour profiles are
        left out too, in a JPEG and in a PNG with transparency."""
        import io

        from PIL import Image, ImageCms, PngImagePlugin

        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        exif = Image.Exif()
        exif[0x010F] = "SecretPhoneMaker"
        jpeg = io.BytesIO()
        Image.new("RGB", (800, 600), (10, 120, 200)).save(
            jpeg,
            "JPEG",
            exif=exif,
            icc_profile=profile,
            comment=b"secret-comment",
            xmp=b"<x:xmpmeta>secret-xmp-author</x:xmpmeta>",
        )
        chunks = PngImagePlugin.PngInfo()
        chunks.add_text("Author", "secret-png-author")
        chunks.add_itxt("XML:com.adobe.xmp", "<x:xmpmeta>secret-png-xmp</x:xmpmeta>")
        png = io.BytesIO()
        Image.new("RGBA", (300, 300), (0, 0, 255, 128)).save(
            png, "PNG", pnginfo=chunks, icc_profile=profile, exif=exif
        )

        for name, data in (("photo.jpg", jpeg.getvalue()), ("logo.png", png.getvalue())):
            dojo = make_dojo(f"Dojo {name}")
            dojo.icon = self.upload(name, data)
            dojo.save()
            with dojo.icon.open("rb") as stored:
                raw = stored.read()
            for secret in (b"secret", b"xmpmeta", b"Author"):
                self.assertNotIn(secret, raw, name)
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(dict(image.getexif()), {}, name)
                left = set(image.info) & {"icc_profile", "exif", "xmp", "comment", "Author", "XML:com.adobe.xmp"}
                self.assertEqual(left, set(), name)

    def test_a_banner_keeps_more_pixels_and_transparency_stays_png(self):
        from events.models import Event

        event = Event(
            dojo=make_dojo("Ghent"), name="Session", start_time=timezone.now(), end_time=timezone.now(), places=5
        )
        event.image = self.upload("banner.jpg", self.jpeg(size=(4000, 1000)))
        event.save()
        self.assertEqual(self.stored(event.image)[1], (1600, 400))
        dojo = make_dojo("Antwerp")
        dojo.icon = self.upload("logo.png", self.png(), "image/png")
        dojo.save()
        image_format, size, mode, _ = self.stored(dojo.icon)
        self.assertEqual((image_format, size, mode), ("PNG", (300, 300), "RGBA"))

    def test_a_standard_image_is_linked_as_it_is(self):
        dojo = make_dojo("Ghent")
        name = sorted(p.name for p in image_library.LIBRARY_DIRS["dojos"].iterdir() if p.is_file())[0]
        image_library.use_library_image(dojo, "icon", "dojos", name, save=True)
        dojo.refresh_from_db()
        self.assertEqual(dojo.icon.name, f"library/dojos/{name}")

    def test_a_replaced_upload_is_deleted_once_committed(self):
        dojo = make_dojo("Ghent")
        dojo.icon = self.upload("first.jpg", self.jpeg())
        dojo.save()
        first = dojo.icon.name
        dojo.icon = self.upload("second.jpg", self.jpeg())
        with self.captureOnCommitCallbacks(execute=True):
            dojo.save()
        self.assertFalse(dojo.icon.storage.exists(first))
        self.assertTrue(dojo.icon.storage.exists(dojo.icon.name))
        # A save that doesn't touch the icon deletes nothing.
        with self.captureOnCommitCallbacks(execute=True):
            dojo.save(update_fields=["name"])
            dojo.save()
        self.assertTrue(dojo.icon.storage.exists(dojo.icon.name))

    def test_a_deleted_row_takes_its_upload_along_unless_another_row_uses_it(self):
        first, second = make_dojo("Ghent"), make_dojo("Antwerp")
        first.icon = self.upload("shared.jpg", self.jpeg())
        first.save()
        Dojo.objects.filter(pk=second.pk).update(icon=first.icon.name)
        name = first.icon.name
        with self.captureOnCommitCallbacks(execute=True):
            first.delete()
        self.assertTrue(default_storage_exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            Dojo.objects.get(pk=second.pk).delete()
        self.assertFalse(default_storage_exists(name))

    def test_a_standard_image_is_never_deleted(self):
        dojo = make_dojo("Ghent")
        name = sorted(p.name for p in image_library.LIBRARY_DIRS["dojos"].iterdir() if p.is_file())[0]
        image_library.use_library_image(dojo, "icon", "dojos", name, save=True)
        library_name = dojo.icon.name
        self.assertTrue(default_storage_exists(library_name))
        dojo.icon = self.upload("own.jpg", self.jpeg())
        with self.captureOnCommitCallbacks(execute=True):
            dojo.save()
            dojo.delete()
        self.assertTrue(default_storage_exists(library_name))

    def test_too_big_or_too_many_pixels_is_refused_with_a_reason(self):
        from django.core.exceptions import ValidationError

        from core import uploads

        with self.assertRaisesMessage(ValidationError, "it can be at most 10 MB"):
            uploads.validate_image_upload(self.upload("big.jpg", b"\xff\xd8\xff" + b"0" * (11 * 1024 * 1024)))
        with self.assertRaisesMessage(ValidationError, "it can be at most 40."):
            uploads.validate_image_upload(self.upload("huge.png", self.png(size=(8000, 6000), alpha=False)))
        uploads.validate_image_upload(self.upload("fine.jpg", self.jpeg()))

    def test_the_admin_can_save_a_row_whose_existing_file_breaks_the_rules(self):
        dojo = make_dojo("Ghent")
        Dojo.objects.filter(pk=dojo.pk).update(icon="dojos/old-and-huge.jpg")
        dojo.refresh_from_db()
        dojo.full_clean()  # an existing file isn't checked again

    def test_the_forms_show_the_limits(self):
        from dojos.forms import DojoProfileForm

        self.assertIn("at most 10 MB", str(DojoProfileForm().fields["icon"].help_text))

    def test_the_background_check_document_must_be_a_pdf_jpeg_or_png(self):
        from applications.forms import BackgroundCheckUploadForm

        def form(name, data):
            return BackgroundCheckUploadForm(
                data={}, files={"document": self.upload(name, data, "application/octet-stream")}
            )

        self.assertTrue(form("extract.pdf", b"%PDF-1.7\n...").is_valid())
        self.assertTrue(form("scan.jpg", self.jpeg(size=(100, 100))).is_valid())
        self.assertTrue(form("scan.png", self.png(size=(10, 10))).is_valid())
        refused = form("extract.pdf", b"MZ\x90\x00 an executable")
        self.assertFalse(refused.is_valid())
        self.assertEqual(refused.errors["document"], ["Upload a PDF, JPEG or PNG file."])
        too_big = form("extract.pdf", b"%PDF-" + b"0" * (11 * 1024 * 1024))
        self.assertIn("at most 10 MB", too_big.errors["document"][0])


def default_storage_exists(name):
    from django.core.files.storage import default_storage

    return default_storage.exists(name)


class CiTestReportTests(TestCase):
    """.github/scripts/test_report.py: the Tests workflow's summary and the
    failed tests marked on the code, from the suite's JUnit XML."""

    XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="events.tests.BookingTests" tests="3" file="events/tests.py">
    <testcase classname="events.tests.BookingTests" name="test_fine" time="0.250" file="events/tests.py" line="10"/>
    <testcase classname="events.tests.BookingTests" name="test_broken" time="1.500" file="events/tests.py" line="20">
      <failure type="AssertionError" message="23 != 22 : overbooked, 50%"><![CDATA[Traceback (most recent call last):
  File "{root}/events/tests.py", line 24, in test_broken
    self.assertEqual(confirmed, 22)
  File "/usr/local/lib/python3.14/site-packages/django/test/testcases.py", line 1, in x
AssertionError: 23 != 22 : overbooked, 50%]]></failure>
    </testcase>
    <testcase classname="events.tests.BookingTests" name="test_later" time="0" file="events/tests.py" line="30">
      <skipped message="not yet"/>
    </testcase>
  </testsuite>
  <testsuite name="core.tests.HomeTests" tests="1" file="core/tests.py">
    <testcase classname="core.tests.HomeTests" name="test_home" time="0.100" file="core/tests.py" line="5">
      <error type="ValueError" message="&lt;b&gt;bad&lt;/b&gt;"><![CDATA[Traceback (most recent call last):
ValueError: <b>bad</b>]]></error>
    </testcase>
  </testsuite>
</testsuites>
"""

    def setUp(self):
        import importlib.util
        import tempfile
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "test_report", Path(settings.BASE_DIR) / ".github" / "scripts" / "test_report.py"
        )
        self.report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.report)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = folder.name
        self.xml = Path(folder.name) / "junit.xml"
        self.xml.write_text(self.XML.replace("{root}", self.root))

    def test_a_failure_is_marked_on_the_line_where_it_failed(self):
        cases = self.report.read([self.xml])
        lines = self.report.annotations(cases, self.root)
        self.assertEqual(len(lines), 2)
        # The last frame inside the repository, not Django's own; the title's : and the message's % escaped.
        self.assertEqual(
            lines[0],
            "::error file=events/tests.py,line=24,title=Failed%3A events.tests.BookingTests.test_broken"
            "::23 != 22 : overbooked, 50%25",
        )
        # Without a frame in the repository: the test's own line.
        self.assertTrue(lines[1].startswith("::error file=core/tests.py,line=5,title=Error%3A core.tests.HomeTests"))

    def test_the_summary_has_the_totals_the_apps_the_failures_and_the_slowest(self):
        text = self.report.summary(self.report.read([self.xml]))
        self.assertIn("❌ **1 failed, 1 error** of 4 tests (2 s of test time), 1 skipped", text)
        self.assertIn("| `events` | 3 | ❌ 1 | 1 | 2 s |", text)
        self.assertIn("| `core` | 1 | ❌ 1 | 0 | 0 s |", text)
        self.assertIn("<code>events.tests.BookingTests.test_broken</code>: 23 != 22 : overbooked, 50%", text)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", text)  # a message can't add HTML to the page
        self.assertIn("| `events.tests.BookingTests.test_broken` | 1.5 s |", text)

    def test_all_passing_and_nothing_found(self):
        passing = self.xml.parent / "passing.xml"
        passing.write_text(
            '<testsuites><testsuite><testcase classname="a.tests.T" name="test_x" time="61" file="a/tests.py" line="1"/>'
            "</testsuite></testsuites>"
        )
        self.assertIn(
            "✅ **All 1 test passed** (1 min 1 s of test time)", self.report.summary(self.report.read([passing]))
        )
        self.assertIn("No test results were found", self.report.summary([]))

    def test_it_writes_to_the_runs_summary_and_never_fails(self):
        from io import StringIO
        from unittest import mock

        target = self.xml.parent / "summary.md"
        with (
            mock.patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(target), "GITHUB_WORKSPACE": self.root}),
            mock.patch("sys.stdout", new_callable=StringIO) as out,
        ):
            self.assertEqual(
                self.report.main(["test_report.py", str(self.xml), str(self.xml.parent / "missing.xml")]), 0
            )
        self.assertIn("## Test results", target.read_text())
        self.assertIn("::error file=events/tests.py,line=24", out.getvalue())
