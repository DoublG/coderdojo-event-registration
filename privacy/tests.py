from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase

from accounts.models import Guardianship, Ninja, User
from applications.models import BackgroundCheckHistory
from privacy import registry
from privacy.registry import (
    Category,
    Erasure,
    FieldPrivacy,
    LegalBasis,
    Registry,
    anonymise,
    keep,
    personal,
)


class EveryFieldIsClassifiedTests(SimpleTestCase):
    """Every field of every model needs a decision (DATA_MODEL.md §16): a
    new field without an entry in its app's privacy.py fails here, the way
    core.tests.StrNeverQueriesTests guards __str__."""

    def test_every_field_of_every_model_is_classified(self):
        self.assertEqual(
            registry.unclassified(),
            [],
            "classify these in the app's privacy.py (personal, anonymise, keep or not_personal)",
        )

    def test_special_and_criminal_data(self):
        self.assertEqual(registry.get(Ninja).fields["allergies_notes"].category, Category.SPECIAL)
        self.assertIn("champion", registry.get(Ninja).fields["allergies_notes"].seen_by)
        document = registry.get(User).fields["background_check_document"]
        self.assertEqual(document.category, Category.CRIMINAL)
        self.assertFalse(document.export)
        self.assertEqual(registry.get(BackgroundCheckHistory).fields["decision"].category, Category.CRIMINAL)

    def test_secrets_are_never_exported(self):
        for entry in registry.registered():
            for name, spec in entry.fields.items():
                if spec.category == Category.SECURITY and name not in ("last_login", "must_change_password"):
                    self.assertFalse(spec.export, f"{entry.label}.{name}")

    def test_model_defaults_fill_the_fields(self):
        relation = registry.get(Guardianship).fields["relation"]
        self.assertEqual(relation.legal_basis, LegalBasis.CONTRACT)
        self.assertEqual(relation.retention, "child")
        self.assertTrue(relation.seen_by)

    def test_whole_models_declared_not_personal(self):
        from geo.models import Municipality

        entry = registry.get(Municipality)
        self.assertFalse(entry.is_personal)
        self.assertTrue(entry.not_personal_reason)
        self.assertEqual(registry.unclassified([Municipality]), [])


class RegistryValidationTests(SimpleTestCase):
    """A declaration with a mistake raises when it's registered, not later."""

    def register(self, **kwargs):
        options = dict(purpose="Test", legal_basis=LegalBasis.CONTRACT, retention="child", seen_by="The family")
        options.update(kwargs)
        return Registry().register(Guardianship, **options)

    def test_a_complete_declaration(self):
        entry = self.register(
            fields={("guardian", "ninja"): personal(Category.CHILD), "relation": keep(Category.CHILD, "why")},
            not_personal=["id"],
        )
        self.assertEqual(entry.fields["ninja"].on_erasure, Erasure.DELETE)
        self.assertEqual(entry.fields["relation"].reason, "why")

    def test_missing_fields_are_reported(self):
        site = Registry()
        site.register(
            Guardianship,
            purpose="Test",
            legal_basis=LegalBasis.CONTRACT,
            retention="child",
            seen_by="The family",
            fields={"guardian": personal(Category.CHILD)},
        )
        self.assertEqual(
            site.unclassified([Guardianship, Ninja]),
            [
                "accounts.Guardianship.id",
                "accounts.Guardianship.ninja",
                "accounts.Guardianship.relation",
                "accounts.Guardianship.created_at",
                "accounts.Guardianship.consent_given_at",
                "accounts.Guardianship.consent_wording_version",
                "accounts.Ninja",
            ],
        )

    def test_mistakes_raise(self):
        mistakes = {
            "no field": dict(fields={"nope": personal(Category.CHILD)}),
            "without a reason": dict(fields={"relation": keep(Category.CHILD, "")}),
            "without a replacement": dict(fields={"relation": FieldPrivacy(Category.CHILD, Erasure.ANONYMISE)}),
            "unknown retention": dict(fields={"relation": personal(Category.CHILD, retention="forever")}),
            "unknown legal basis": dict(legal_basis="because", fields={"relation": personal(Category.CHILD)}),
            "unknown category": dict(fields={"relation": personal("secret")}),
            "no purpose": dict(purpose="", fields={"relation": personal(Category.CHILD)}),
            "no seen_by": dict(seen_by="", fields={"relation": personal(Category.CHILD)}),
            "classified twice": dict(
                fields={"relation": personal(Category.CHILD), ("relation",): anonymise(Category.CHILD, "")}
            ),
            "both personal and not personal": dict(
                fields={"relation": personal(Category.CHILD)}, not_personal=["relation"]
            ),
        }
        for message, kwargs in mistakes.items():
            with self.subTest(message), self.assertRaisesMessage(ImproperlyConfigured, message):
                self.register(**kwargs)

    def test_a_model_is_registered_once(self):
        site = Registry()
        site.register_not_personal(Guardianship, "test")
        with self.assertRaisesMessage(ImproperlyConfigured, "registered twice"):
            site.register_not_personal(Guardianship, "test")

    def test_not_personal_needs_a_reason(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "without a reason"):
            Registry().register_not_personal(Guardianship, "")


class PrivacyRegisterTests(SimpleTestCase):
    """manage.py privacy_register writes the art. 30 register from the classification."""

    def test_markdown(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("privacy_register", stdout=out)
        text = out.getvalue()
        self.assertIn("# Register of processing activities", text)
        self.assertIn("## Special category (art. 9): health", text)
        self.assertIn("accounts.Ninja: allergies_notes", text)
        self.assertIn("| child | Until N years after", text)
        self.assertIn("| geo.Municipality |", text)
        self.assertNotIn("accounts.Ninja: id", text)

    def test_csv_has_a_row_per_personal_field(self):
        import csv
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("privacy_register", format="csv", stdout=out)
        table = list(csv.DictReader(StringIO(out.getvalue())))
        personal_fields = sum(len(entry.fields) for entry in registry.registered())
        self.assertEqual(len(table), personal_fields)
        allergies = next(row for row in table if row["field"] == "allergies_notes")
        self.assertEqual((allergies["category"], allergies["legal_basis"]), ("special", "consent"))
        document = next(row for row in table if row["field"] == "background_check_document")
        self.assertEqual(document["export"], "no")

    def test_erasure_is_named_per_field_when_it_differs(self):
        from privacy.register import as_markdown

        text = as_markdown()
        self.assertIn("username: anonymise (replaced by 'former-{pk}')", text)
        self.assertIn("| mailing.MailPreference: user, category, subscribed, changed_at |", text)


class ExportTests(TestCase):
    """privacy.export: a person's data, their children's, and nobody else's."""

    def setUp(self):
        from datetime import date, timedelta

        from django.utils import timezone

        from applications.models import Application
        from dojos.testing import make_dojo
        from events.models import Belt, Event, NinjaBelt, Registration
        from mailing.models import EmailSuppression, MailPreference

        self.parent = User.objects.create(username="an", email="an@example.com", first_name="An")
        self.parent.set_password("secret")
        self.parent.save()
        self.child = Ninja.objects.create(name="Lotte", allergies_notes="Peanuts")
        Guardianship.objects.create(guardian=self.parent, ninja=self.child)
        self.sibling = Ninja.objects.create(name="Mats")
        Guardianship.objects.create(guardian=self.parent, ninja=self.sibling)
        self.other_child = Ninja.objects.create(name="Someone else")

        dojo = make_dojo("Ghent")
        start = timezone.now() + timedelta(days=3)
        self.event = Event.objects.create(
            name="Coding Saturday", dojo=dojo, places=10, start_time=start, end_time=start + timedelta(hours=2)
        )
        Registration.objects.create(event=self.event, ninja=self.child, waiting_list=False, position=1)
        Registration.objects.create(event=self.event, ninja=self.other_child, waiting_list=False, position=2)
        NinjaBelt.objects.create(
            ninja=self.child, belt=Belt.objects.create(level=1, name="White"), awarded_on=date(2026, 1, 1)
        )
        MailPreference.objects.create(user=self.parent, category="newsletter", subscribed=True)
        EmailSuppression.objects.create(email="AN@example.com", reason="manual")
        self.reviewer = User.objects.create(username="reviewer", first_name="Rita")
        Application.objects.create(
            account=self.parent, kind=Application.MENTOR, message="I like Scratch", decided_by=self.reviewer
        )
        BackgroundCheckHistory.objects.create(
            account=self.parent, decision="validated", reviewed_by=self.reviewer, reviewed_at=timezone.now()
        )

    def export(self, user):
        from privacy.export import export_person

        return export_person(user)

    def test_the_account_and_its_children(self):
        export = self.export(self.parent)
        data = export["data"]
        self.assertEqual(sorted(export["children"]), ["Lotte", "Mats"])
        self.assertEqual([r["username"] for r in data["accounts.User"]["records"]], ["an"])
        self.assertEqual(sorted(r["name"] for r in data["accounts.Ninja"]["records"]), ["Lotte", "Mats"])
        lotte = next(r for r in data["accounts.Ninja"]["records"] if r["name"] == "Lotte")
        self.assertEqual(lotte["allergies_notes"], "Peanuts")
        self.assertEqual([r["ninja"] for r in data["events.Registration"]["records"]], ["Lotte"])
        self.assertIn("Coding Saturday", data["events.Registration"]["records"][0]["event"])
        self.assertEqual(data["events.NinjaBelt"]["records"][0]["belt"], "White")
        self.assertEqual(data["mailing.MailPreference"]["records"][0]["category"], "newsletter")
        self.assertEqual(data["mailing.EmailSuppression"]["records"][0]["reason"], "manual")
        self.assertEqual(data["applications.Application"]["records"][0]["message"], "I like Scratch")
        self.assertEqual(data["applications.BackgroundCheckHistory"]["records"][0]["decision"], "validated")
        self.assertTrue(data["accounts.User"]["purpose"])

    def test_never_secrets_ids_or_someone_else(self):
        from privacy.export import export_json

        text = export_json(self.parent)
        record = self.export(self.parent)["data"]["accounts.User"]["records"][0]
        for secret in ("password", "background_check_token", "background_check_document", "id"):
            self.assertNotIn(secret, record)
        self.assertNotIn(self.parent.password, text)
        self.assertNotIn("Someone else", text)
        # The reviewers' names are theirs, not the applicant's.
        self.assertNotIn("reviewer", text)
        self.assertNotIn("Rita", text)

    def test_a_ninja_login_gets_only_its_own(self):
        login = User.objects.create(username="lotte", account_type=User.NINJA, email="lotte@example.com")
        self.child.account = login
        self.child.save()
        export = self.export(login)
        self.assertEqual(export["children"], ["Lotte"])
        data = export["data"]
        self.assertEqual([r["username"] for r in data["accounts.User"]["records"]], ["lotte"])
        self.assertEqual([r["name"] for r in data["accounts.Ninja"]["records"]], ["Lotte"])
        self.assertNotIn("mailing.MailPreference", data)
        from privacy.export import export_json

        text = export_json(login)
        self.assertNotIn("Mats", text)
        self.assertNotIn("an@example.com", text)

    def test_the_parent_gets_the_childs_login(self):
        login = User.objects.create(username="lotte", account_type=User.NINJA)
        self.child.account = login
        self.child.save()
        usernames = [r["username"] for r in self.export(self.parent)["data"]["accounts.User"]["records"]]
        self.assertEqual(sorted(usernames), ["an", "lotte"])

    def test_json_file(self):
        import json

        from privacy.export import export_filename, export_json

        self.assertEqual(json.loads(export_json(self.parent))["account"], "an")
        self.assertTrue(export_filename(self.parent).startswith("coderdojo-data-an-"))


class ExportCoverageTests(SimpleTestCase):
    """Every model with personal data to export says whose rows are whose
    (`subjects`), or why it isn't part of a person's export."""

    EXCEPTIONS = {
        "dojos.Dojo": "a dojo's contact details belong with the dojo; its team's own data is in their export",
        "events.Event": "a session's team and children are exported through memberships and registrations",
        "content.Testimonial": "a quote on the site with a name, not linked to an account",
    }

    def test_every_exported_model_has_subjects(self):
        missing = [
            entry.label
            for entry in registry.registered()
            if any(spec.export for spec in entry.fields.values())
            and not entry.subjects
            and entry.label not in self.EXCEPTIONS
        ]
        self.assertEqual(missing, [])

    def test_unknown_subject_lookup_raises(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "no lookup"):
            Registry().register(Guardianship, subjects={"account": "nobody"})


class DownloadViewTests(TestCase):
    """The family's Download my data, and the organisation dashboard's Privacy page."""

    def setUp(self):
        from django.core.cache import cache

        from accounts.models import OrganisationRole

        cache.clear()
        self.parent = User.objects.create(username="an", email="an@example.com", first_name="An", last_name="Peeters")
        self.child = Ninja.objects.create(name="Lotte")
        Guardianship.objects.create(guardian=self.parent, ninja=self.child)
        self.admin = User.objects.create(username="orgadmin")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)

    def test_download_needs_a_login(self):
        from django.urls import reverse

        response = self.client.get(reverse("download_my_data"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_download_my_data(self):
        import json

        from django.urls import reverse

        self.client.force_login(self.parent)
        response = self.client.get(reverse("download_my_data"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertIn('attachment; filename="coderdojo-data-an-', response["Content-Disposition"])
        self.assertEqual(json.loads(response.content)["children"], ["Lotte"])

    def test_one_download_a_minute(self):
        from django.urls import reverse

        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(reverse("download_my_data")).status_code, 200)
        response = self.client.get(reverse("download_my_data"))
        self.assertRedirects(response, reverse("account_home"))

    def test_account_pages_link_to_it(self):
        from django.urls import reverse

        self.client.force_login(self.parent)
        self.assertContains(self.client.get(reverse("account_home")), reverse("download_my_data"))
        # A guardian viewing the child's page doesn't get the child's own link.
        self.assertNotContains(
            self.client.get(reverse("ninja_detail", args=[self.child.id])), reverse("download_my_data")
        )
        login = User.objects.create(username="lotte", account_type=User.NINJA)
        self.child.account = login
        self.child.save()
        self.client.force_login(login)
        self.assertContains(
            self.client.get(reverse("ninja_detail", args=[self.child.id])), reverse("download_my_data")
        )

    def test_privacy_page_is_for_the_organisation_admin_only(self):
        from django.urls import reverse

        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(reverse("manage_privacy")).status_code, 404)
        self.assertEqual(self.client.get(reverse("manage_privacy_export", args=[self.parent.id])).status_code, 404)

    def test_privacy_page_finds_accounts_by_name_email_or_child(self):
        from django.urls import reverse

        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage_privacy"))
        self.assertTemplateUsed(response, "privacy/manage/privacy.html")
        for query in ("peeters", "an@example", "Lotte"):
            response = self.client.get(reverse("manage_privacy"), {"q": query})
            self.assertEqual(list(response.context["accounts"]), [self.parent], query)
            self.assertContains(response, reverse("manage_privacy_export", args=[self.parent.id]))

    def test_organisation_export(self):
        import json

        from django.urls import reverse

        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage_privacy_export", args=[self.parent.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["account"], "an")
        # The organisation isn't held to the family's once a minute.
        self.assertEqual(self.client.get(reverse("manage_privacy_export", args=[self.parent.id])).status_code, 200)


class ErasureTests(TestCase):
    """privacy.erasure: a family erased through the classification, a
    volunteer cleaned, someone else's links, the audit log, and a replay."""

    def setUp(self):
        from datetime import date, timedelta

        from django.utils import timezone

        from applications.models import Application
        from dojos.testing import add_member, make_dojo
        from events.models import Belt, Event, NinjaBelt, Registration, RegistrationCancellation
        from mailing.models import ConsentEvent, EmailMessage, EmailSuppression, MailPreference
        from notifications.models import Notification

        self.parent = User.objects.create(
            username="an",
            email="an@example.com",
            first_name="An",
            last_name="Peeters",
            phone="0470",
            postal_code="9000",
        )
        self.parent.set_password("secret")
        self.parent.save()
        self.other_parent = User.objects.create(username="bart", email="bart@example.com")
        self.child = Ninja.objects.create(name="Lotte", allergies_notes="Peanuts", date_of_birth=date(2015, 3, 1))
        Guardianship.objects.create(guardian=self.parent, ninja=self.child)
        self.login = User.objects.create(username="lotte", email="lotte@example.com", account_type=User.NINJA)
        self.child.account = self.login
        self.child.save()
        # Mats has another guardian, so he stays.
        self.sibling = Ninja.objects.create(name="Mats")
        Guardianship.objects.create(guardian=self.parent, ninja=self.sibling)
        Guardianship.objects.create(guardian=self.other_parent, ninja=self.sibling)

        self.dojo = make_dojo("Ghent")
        start = timezone.now() - timedelta(days=30)
        self.event = Event.objects.create(
            name="Coding Saturday", dojo=self.dojo, places=10, start_time=start, end_time=start + timedelta(hours=2)
        )
        self.registration = Registration.objects.create(
            event=self.event, ninja=self.child, waiting_list=False, position=1, attended=True
        )
        NinjaBelt.objects.create(
            ninja=self.child, belt=Belt.objects.create(level=1, name="White"), awarded_on=date(2026, 1, 1)
        )
        # A cancellation for the sibling, made by the parent: only that link goes.
        self.cancellation = RegistrationCancellation.objects.create(
            ninja=self.sibling, event=self.event, was_waitlisted=False, cancelled_by=self.parent
        )
        MailPreference.objects.create(user=self.parent, category="newsletter", subscribed=True)
        ConsentEvent.objects.create(user=self.parent, category="newsletter", subscribed=True, source="signup")
        EmailSuppression.objects.create(email="AN@example.com", reason="manual")
        self.mail = EmailMessage.objects.create(
            user=self.parent,
            recipient="an@example.com",
            subject="Hi An",
            body="Dear An",
            category="service",
            template_key="x",
            message_id="<1@example.com>",
            idempotency_key="k:1",
        )
        Notification.objects.create(recipient=self.parent, text="Hello")
        Application.objects.create(account=self.parent, kind=Application.MENTOR, message="I like Scratch")
        BackgroundCheckHistory.objects.create(account=self.parent, decision="validated", reviewed_at=timezone.now())
        self.mentor = User.objects.create(
            username="jan",
            email="jan@example.com",
            first_name="Jan",
            last_name="Claes",
            title="Engineer",
            bio="Likes Python",
        )
        self.membership = add_member(self.dojo, self.mentor)
        self.event.team.add(self.membership)

    def test_a_family_is_erased(self):
        from events.models import NinjaBelt, Registration
        from mailing.models import ConsentEvent, EmailMessage, EmailSuppression, MailPreference
        from notifications.models import Notification
        from privacy.erasure import erase_person
        from privacy.models import ErasureRecord

        self.assertEqual(erase_person(self.parent), [self.child])

        parent = User.objects.get(pk=self.parent.pk)
        self.assertEqual(parent.username, f"former-{parent.pk}")
        self.assertEqual((parent.first_name, parent.last_name), ("Former member", f"#{parent.pk}"))
        self.assertEqual((parent.email, parent.phone, parent.postal_code), ("", "", ""))
        self.assertFalse(parent.is_active)
        self.assertFalse(parent.has_usable_password())
        child = Ninja.objects.get(pk=self.child.pk)
        self.assertEqual(child.name, f"Former ninja #{child.pk}")
        self.assertEqual((child.allergies_notes, child.date_of_birth, child.account), ("", None, None))
        login = User.objects.get(pk=self.login.pk)
        self.assertEqual((login.username, login.email, login.is_active), (f"former-{login.pk}", "", False))

        # The session keeps its numbers; the child's own history goes.
        self.assertTrue(Registration.objects.filter(pk=self.registration.pk, ninja=child, attended=True).exists())
        self.assertFalse(NinjaBelt.objects.filter(ninja=child).exists())
        self.assertFalse(Guardianship.objects.filter(guardian=parent).exists())
        self.assertFalse(MailPreference.objects.filter(user=parent).exists())
        self.assertFalse(Notification.objects.filter(recipient=parent).exists())
        self.assertFalse(parent.applications.exists())
        # Kept, with their reasons: proof of consent, the block, the check decisions.
        self.assertTrue(ConsentEvent.objects.filter(user=parent).exists())
        self.assertTrue(EmailSuppression.objects.filter(email="AN@example.com").exists())
        self.assertTrue(BackgroundCheckHistory.objects.filter(account=parent).exists())
        # The mail row stays for statistics, without the person.
        mail = EmailMessage.objects.get(pk=self.mail.pk)
        self.assertEqual((mail.user, mail.recipient, mail.subject, mail.body), (None, "", "", ""))
        self.assertEqual((mail.idempotency_key, mail.category), (None, "service"))

        # Mats has another guardian: he stays, as does their link.
        sibling = Ninja.objects.get(pk=self.sibling.pk)
        self.assertEqual(sibling.name, "Mats")
        self.assertTrue(Guardianship.objects.filter(guardian=self.other_parent, ninja=sibling).exists())
        self.cancellation.refresh_from_db()
        self.assertIsNone(self.cancellation.cancelled_by)

        self.assertEqual(
            set(ErasureRecord.objects.values_list("model", "object_id")),
            {("accounts.User", self.parent.pk), ("accounts.User", self.login.pk), ("accounts.Ninja", self.child.pk)},
        )

    def test_a_volunteer_is_cleaned(self):
        from dojos.models import DojoMembership
        from privacy.erasure import erase_person

        erase_person(self.mentor, keep_visible=True)
        mentor = User.objects.get(pk=self.mentor.pk)
        self.assertEqual(mentor.display_name, "Jan Claes")
        self.assertEqual(mentor.team_name, "Jan Claes")
        self.assertEqual((mentor.title, mentor.bio), ("Engineer", "Likes Python"))
        self.assertEqual((mentor.email, mentor.first_name, mentor.is_active), ("", "Former member", False))
        membership = DojoMembership.objects.get(pk=self.membership.pk)
        self.assertEqual(membership.status, DojoMembership.DORMANT)
        self.assertIn(membership, self.event.team.all())

    def test_a_hidden_profile_goes_but_the_name_stays(self):
        from privacy.erasure import erase_person

        User.objects.filter(pk=self.mentor.pk).update(show_on_team_pages=False)
        erase_person(User.objects.get(pk=self.mentor.pk), keep_visible=True)
        mentor = User.objects.get(pk=self.mentor.pk)
        self.assertEqual((mentor.display_name, mentor.title, mentor.bio), ("Jan Claes", "", ""))

    def test_the_audit_log(self):
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        from privacy.erasure import erase_person
        from privacy.models import ErasureRecord

        user_type = ContentType.objects.get_for_model(User)
        about = lambda user: LogEntry.objects.filter(content_type=user_type, object_pk=str(user.pk))  # noqa: E731
        User.objects.get(pk=self.parent.pk).save()  # nothing changed: make sure there's an entry
        self.parent.phone = "0471"
        self.parent.save()
        entry = about(self.parent).latest("pk")
        LogEntry.objects.filter(pk=entry.pk).update(actor=self.parent, actor_email="an@example.com")
        count = LogEntry.objects.count()

        erase_person(self.parent)
        # Cleared, not removed, on request; and the erasure itself isn't recorded.
        self.assertEqual(LogEntry.objects.count(), count)
        entry.refresh_from_db()
        self.assertEqual((entry.object_repr, entry.changes_text, entry.actor_email), ("", "", None))
        self.assertEqual(entry.actor_id, self.parent.pk)

        self.mentor.phone = "0472"
        self.mentor.save()
        self.assertTrue(about(self.mentor).exists())
        erase_person(self.mentor, reason=ErasureRecord.RETENTION, keep_visible=True)
        self.assertFalse(about(self.mentor).exists())

    def test_replay_after_a_restore(self):
        from privacy.erasure import erase_person, replay_erasures

        erase_person(self.parent)
        # A backup from before the erasure is restored.
        User.objects.filter(pk=self.parent.pk).update(email="an@example.com", first_name="An")
        Ninja.objects.filter(pk=self.child.pk).update(name="Lotte")
        self.assertEqual(replay_erasures(), 3)
        self.assertEqual(User.objects.get(pk=self.parent.pk).email, "")
        self.assertEqual(Ninja.objects.get(pk=self.child.pk).name, f"Former ninja #{self.child.pk}")


class RetentionTests(TestCase):
    """privacy.retention: two years after the last login, with reminder
    mails 30 and 7 days before, and the exceptions."""

    def setUp(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("load_mail_templates", stdout=StringIO())
        self.parent = self.account("an", days_ago=700)
        self.child = Ninja.objects.create(name="Lotte")
        Guardianship.objects.create(guardian=self.parent, ninja=self.child)

    def account(self, username, days_ago, **fields):
        from datetime import timedelta

        from django.utils import timezone

        return User.objects.create(
            username=username,
            email=f"{username}@example.com",
            first_name=username.title(),
            last_login=timezone.now() - timedelta(days=days_ago),
            **fields,
        )

    def on(self, days):
        """Pretend it's `days` from now."""
        from datetime import timedelta
        from unittest import mock

        from django.utils import timezone

        moment = timezone.now() + timedelta(days=days)
        return mock.patch("django.utils.timezone.now", return_value=moment)

    def run_job(self, days=0):
        from privacy.retention import apply_retention

        with self.on(days):
            return apply_retention()

    def mails(self, user):
        from mailing.models import EmailMessage

        return list(EmailMessage.objects.filter(user=user, template_key="account_deletion_reminder").order_by("pk"))

    def erased(self, user):
        from privacy.erasure import is_erased

        return is_erased(user)

    def test_reminders_then_erasure(self):
        self.assertEqual(self.run_job()["reminders"], 1)
        [mail] = self.mails(self.parent)
        self.assertEqual(mail.status, "pending")
        self.assertIn("Lotte", mail.body)
        self.assertIn("/login/", mail.body)
        self.assertEqual(mail.idempotency_key.split(":")[:3], ["account-deletion", str(self.parent.pk), "30"])
        # Safe to run twice.
        self.assertEqual(self.run_job()["reminders"], 0)
        self.assertEqual(self.run_job(22)["reminders"], 0)
        self.assertEqual(self.run_job(23)["reminders"], 1)
        self.assertEqual(len(self.mails(self.parent)), 2)
        self.assertEqual(self.run_job(29)["erased"], 0)
        self.assertEqual(self.run_job(30)["erased"], 1)
        self.assertTrue(self.erased(self.parent))
        self.assertEqual(Ninja.objects.get(pk=self.child.pk).name, f"Former ninja #{self.child.pk}")
        # Erased accounts are left alone from then on.
        self.assertEqual(self.run_job(400)["reminders"], 0)

    def test_recent_accounts_are_left_alone(self):
        self.account("recent", days_ago=100)
        self.account("new", days_ago=0)
        self.assertEqual(self.run_job()["reminders"], 1)  # only An

    def test_never_without_a_months_notice(self):
        """An account already long overdue gets its 30 days."""
        late = self.account("late", days_ago=2000)
        self.run_job()
        self.assertEqual(len(self.mails(late)), 1)
        self.assertEqual(self.run_job(29)["erased"], 0)
        self.run_job(30)
        self.assertTrue(self.erased(late))

    def test_logging_in_moves_the_date(self):
        from django.utils import timezone

        from privacy.models import RetentionNotice

        self.run_job()
        User.objects.filter(pk=self.parent.pk).update(last_login=timezone.now())
        self.run_job(30)
        self.assertFalse(self.erased(self.parent))
        self.assertFalse(RetentionNotice.objects.filter(account=self.parent).exists())

    def test_a_childs_own_login_keeps_the_family_in_use(self):
        from django.utils import timezone

        from privacy.models import RetentionNotice

        login = self.account("lotte", days_ago=1000, account_type=User.NINJA)
        self.child.account = login
        self.child.save()
        self.run_job()
        self.assertEqual(len(self.mails(self.parent)), 1)
        # Lotte logs in: the reminder is about a period that ended, and the
        # family's two years start again.
        User.objects.filter(pk=login.pk).update(last_login=timezone.now())
        self.run_job(30)
        self.assertEqual(len(self.mails(self.parent)), 1)
        self.assertFalse(self.erased(self.parent))
        self.assertFalse(RetentionNotice.objects.filter(account=self.parent).exists())
        self.run_job(700)
        self.assertEqual(len(self.mails(self.parent)), 2)

    def test_organisation_roles_and_superusers_are_left_alone(self):
        from accounts.models import OrganisationRole

        board = self.account("board", days_ago=2000)
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        root = self.account("root", days_ago=2000, is_superuser=True)
        self.run_job()
        self.run_job(40)
        self.assertEqual(self.mails(board) + self.mails(root), [])
        self.assertFalse(self.erased(board) or self.erased(root))
        # Once the role ends, the rule applies again with the usual notice.
        OrganisationRole.objects.filter(account=board).delete()
        self.run_job(41)
        self.assertEqual(len(self.mails(board)), 1)
        self.run_job(70)
        self.assertFalse(self.erased(board))
        self.run_job(71)
        self.assertTrue(self.erased(board))

    def test_a_volunteer_is_cleaned_not_erased(self):
        from dojos.testing import add_member, make_dojo
        from privacy.models import ErasureRecord

        mentor = self.account("jan", days_ago=700, last_name="Claes")
        add_member(make_dojo("Ghent"), mentor)
        self.run_job()
        self.assertIn("name on the sessions", self.mails(mentor)[0].body)
        self.run_job(23)
        self.run_job(30)
        self.assertTrue(ErasureRecord.objects.get(object_id=mentor.pk, model="accounts.User").keep_visible)
        self.assertEqual(User.objects.get(pk=mentor.pk).team_name, "Jan Claes")

    def test_a_champion_of_an_active_dojo_waits_for_the_handover(self):
        from django.urls import reverse

        from accounts.models import OrganisationRole
        from dojos.models import DojoMembership
        from dojos.team import transfer_champion
        from dojos.testing import add_member, make_dojo, make_mentor
        from notifications.models import Notification
        from privacy.retention import champions_needing_attention

        champion = self.account("chris", days_ago=700)
        dojo = make_dojo("Ghent", champion=champion)
        mentor = make_mentor(username="mia")
        mentor_membership = add_member(dojo, mentor)
        self.run_job()
        self.assertIn("still the champion of Ghent", self.mails(champion)[0].body)
        self.assertEqual(Notification.objects.filter(recipient=mentor).count(), 1)
        self.assertFalse(Notification.objects.filter(recipient=champion).exists())
        [row] = champions_needing_attention()
        self.assertEqual((row["dojo"], row["champion"], row["passed"]), (dojo, champion, False))

        admin = User.objects.create(username="orgadmin")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        self.client.force_login(admin)
        response = self.client.get(reverse("manage_privacy"))
        self.assertContains(response, "Needs attention")
        self.assertContains(response, reverse("admin:dojos_dojo_change", args=[dojo.id]))
        self.assertContains(response, 'class="cd-admin-nav__count caption"')

        self.run_job(23)
        self.assertEqual(self.run_job(30)["held_back"], 1)
        self.assertEqual(self.run_job(31)["held_back"], 1)
        self.assertFalse(self.erased(champion))
        # Told once more when the date passed, not every night.
        self.assertEqual(Notification.objects.filter(recipient=mentor).count(), 2)
        with self.on(31):
            self.assertTrue(champions_needing_attention()[0]["passed"])

        transfer_champion(dojo, DojoMembership.objects.get(user=champion), mentor_membership)
        self.assertEqual(champions_needing_attention(), [])
        self.assertEqual(self.run_job(32)["cleaned"], 1)
        self.assertTrue(self.erased(champion))

    def test_a_childs_login_goes_with_the_family(self):
        """No date or mail of its own: the guardian gets the notice, and the
        login is erased with the family."""
        login = self.account("lotte", days_ago=1000, account_type=User.NINJA)
        self.child.account = login
        self.child.save()
        self.run_job()
        self.assertEqual(self.mails(login), [])
        [mail] = self.mails(self.parent)
        self.assertIn("their own login", mail.body)
        self.run_job(23)
        self.assertEqual(self.run_job(30)["erased"], 1)
        login = User.objects.get(pk=login.pk)
        self.assertEqual((login.email, login.is_active), ("", False))
        self.assertTrue(self.erased(login))

    def test_a_ninja_login_is_never_handled_on_its_own(self):
        """A child without a guardian is a manual fix in the admin: left alone."""
        orphan = self.account("orphan", days_ago=2000, account_type=User.NINJA)
        Ninja.objects.create(name="Orphan", account=orphan)
        self.run_job()
        self.run_job(40)
        self.assertEqual(self.mails(orphan), [])
        self.assertFalse(self.erased(orphan))
        self.assertTrue(User.objects.get(pk=orphan.pk).is_active)

    def test_old_audit_log_entries_and_sessions(self):
        from datetime import timedelta

        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType
        from django.contrib.sessions.models import Session
        from django.utils import timezone

        user_type = ContentType.objects.get_for_model(User)
        old = timezone.now() - timedelta(days=800)
        nobody = LogEntry.objects.create(content_type=user_type, object_pk="1", action=1, timestamp=old)
        active = self.account("active", days_ago=1)
        someone = LogEntry.objects.create(content_type=user_type, object_pk="1", action=1, timestamp=old, actor=active)
        LogEntry.objects.filter(pk__in=[nobody.pk, someone.pk]).update(timestamp=old)
        Session.objects.create(session_key="old", session_data="", expire_date=timezone.now() - timedelta(days=1))
        Session.objects.create(session_key="new", session_data="", expire_date=timezone.now() + timedelta(days=1))

        done = self.run_job()
        self.assertEqual(done["audit_log_entries"], 1)
        self.assertFalse(LogEntry.objects.filter(pk=nobody.pk).exists())
        self.assertTrue(LogEntry.objects.filter(pk=someone.pk).exists())
        self.assertEqual(list(Session.objects.values_list("session_key", flat=True)), ["new"])

    def test_the_reminder_renders_in_every_language(self):
        from datetime import date

        from mailing.rendering import render

        for language in ("en-us", "nl-be", "fr-be"):
            for volunteer in (True, False):
                context = {
                    "recipient_name": "An",
                    "deletion_date": date(2026, 10, 26),
                    "login_url": "https://x/login/",
                    "children": ["Lotte"],
                    "volunteer": volunteer,
                    "keeps_profile": True,
                    "champion_of": ["Ghent"],
                }
                subject, body = render("account_deletion_reminder", language, context)
                self.assertIn("2026", subject, (language, volunteer))
                self.assertIn("https://x/login/", body, (language, volunteer))
                self.assertNotIn("{%", body)


class DeleteAccountTests(TestCase):
    """privacy.deletion: the family's Delete my account and the
    organisation's Delete… on the Privacy page."""

    def setUp(self):
        from accounts.models import OrganisationRole

        self.parent = User.objects.create(username="an", email="an@example.com", first_name="An")
        self.parent.set_password("secret-password-1")
        self.parent.save()
        self.child = Ninja.objects.create(name="Lotte")
        Guardianship.objects.create(guardian=self.parent, ninja=self.child)
        self.shared = Ninja.objects.create(name="Mats")
        Guardianship.objects.create(guardian=self.parent, ninja=self.shared)
        Guardianship.objects.create(guardian=User.objects.create(username="bart"), ninja=self.shared)
        self.admin = User.objects.create(username="orgadmin")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)

    def url(self, name, *args):
        from django.urls import reverse

        return reverse(name, args=args)

    def erased(self, user):
        from privacy.erasure import is_erased

        return is_erased(user)

    def test_the_account_page_links_to_it(self):
        self.client.force_login(self.parent)
        self.assertContains(self.client.get(self.url("account_home")), self.url("delete_my_account"))

    def test_the_preview(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url("delete_my_account"))
        self.assertTemplateUsed(response, "privacy/delete_account.html")
        self.assertEqual(response.context["preview"].children, [self.child])
        self.assertEqual(response.context["preview"].shared_children, [self.shared])
        self.assertContains(response, 'name="password"')

    def test_a_wrong_password_deletes_nothing(self):
        self.client.force_login(self.parent)
        response = self.client.post(self.url("delete_my_account"), {"password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["error"])
        self.assertFalse(self.erased(self.parent))

    def test_the_family_deletes_its_account(self):
        from privacy.models import ErasureRecord

        self.client.force_login(self.parent)
        response = self.client.post(self.url("delete_my_account"), {"password": "secret-password-1"})
        self.assertTemplateUsed(response, "privacy/account_deleted.html")
        self.assertNotIn("_auth_user_id", self.client.session)
        record = ErasureRecord.objects.get(model="accounts.User", object_id=self.parent.pk)
        self.assertEqual((record.reason, record.requested_by), (ErasureRecord.SELF, None))
        self.assertEqual(Ninja.objects.get(pk=self.child.pk).name, f"Former ninja #{self.child.pk}")
        self.assertEqual(Ninja.objects.get(pk=self.shared.pk).name, "Mats")
        self.assertFalse(User.objects.get(pk=self.parent.pk).is_active)

    def test_not_for_a_childs_own_login(self):
        login = User.objects.create(username="lotte", account_type=User.NINJA)
        self.client.force_login(login)
        self.assertEqual(self.client.get(self.url("delete_my_account")).status_code, 404)

    def test_a_champion_of_an_active_dojo_hands_over_first(self):
        from dojos.testing import make_dojo

        make_dojo("Ghent", champion=self.parent)
        self.client.force_login(self.parent)
        response = self.client.get(self.url("delete_my_account"))
        self.assertContains(response, "champion of Ghent")
        self.assertNotContains(response, 'name="password"')
        self.client.post(self.url("delete_my_account"), {"password": "secret-password-1"})
        self.assertFalse(self.erased(self.parent))

    def test_a_mentor_is_cleaned(self):
        from dojos.testing import add_member, make_dojo
        from privacy.models import ErasureRecord

        add_member(make_dojo("Ghent"), self.parent)
        self.client.force_login(self.parent)
        self.client.post(self.url("delete_my_account"), {"password": "secret-password-1"})
        self.assertTrue(ErasureRecord.objects.get(model="accounts.User", object_id=self.parent.pk).keep_visible)

    def test_the_organisation_page_is_for_the_admin_role_only(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(self.url("manage_privacy_delete", self.parent.pk)).status_code, 404)

    def test_the_organisation_deletes_on_request(self):
        from privacy.models import ErasureRecord

        self.client.force_login(self.admin)
        response = self.client.get(self.url("manage_privacy"), {"q": "an@example"})
        self.assertContains(response, self.url("manage_privacy_delete", self.parent.pk))
        response = self.client.get(self.url("manage_privacy_delete", self.parent.pk))
        self.assertTemplateUsed(response, "privacy/manage/delete.html")
        self.assertContains(response, "Lotte")

        response = self.client.post(self.url("manage_privacy_delete", self.parent.pk), {"confirm": "wrong"})
        self.assertTrue(response.context["error"])
        self.assertFalse(self.erased(self.parent))

        response = self.client.post(self.url("manage_privacy_delete", self.parent.pk), {"confirm": "an"})
        self.assertRedirects(response, self.url("manage_privacy"))
        record = ErasureRecord.objects.get(model="accounts.User", object_id=self.parent.pk)
        self.assertEqual((record.reason, record.requested_by), (ErasureRecord.REQUEST, self.admin))

    def test_an_organisation_role_is_taken_away_first(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url("manage_privacy_delete", self.admin.pk), {"confirm": "orgadmin"})
        self.assertContains(response, "organisation role")
        self.assertFalse(self.erased(self.admin))
