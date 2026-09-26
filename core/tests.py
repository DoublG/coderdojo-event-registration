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
        both = sorted(label for label in self.NOT_RECORDED if auditlog.contains(apps.get_model(label)))
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
            {"category_newsletter": "on", "postal_code": "", "preferred_language": "en-us"},
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
        event = Event.objects.create(name="Coding", dojo=dojo, places=5, start_time=start,
                                     end_time=start + timedelta(hours=2), status=Event.OPEN)
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
        self.event = Event.objects.create(name="Coding", dojo=self.dojo, places=5, start_time=start,
                                          end_time=start + timedelta(hours=2), status=Event.OPEN)
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
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:auditlog_logentry_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:dojos_dojo_auditlog", args=[self.dojo.id])).status_code, 200)
        self.assertContains(self.client.get(reverse("admin:dojos_dojo_changelist")),
                            reverse("admin:dojos_dojo_auditlog", args=[self.dojo.id]))

    def test_the_board_does_not(self):
        self.client.force_login(self.board)
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
