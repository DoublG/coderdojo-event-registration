from datetime import timedelta
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from applications.models import Application
from core.testing import TempMediaMixin, login_data
from dojos.models import Dojo, DojoMembership
from dojos.testing import add_member, make_champion, make_dojo, make_mentor
from events.models import Event, Registration
from geo.models import Municipality

from .models import Guardianship, Ninja, User
from .provisioning import unique_username

PASSWORD = "correct-horse-battery-staple"


def _dob(age):
    """An ISO date of birth for a child of `age` today (mid-year, so it
    never sits on a birthday boundary)."""
    return (timezone.localdate() - timedelta(days=int(age * 365.25) + 180)).isoformat()


# The management form of family sign-up's child rows (accounts.forms.ChildRowsFormSet).
CHILD_ROWS = {"child-TOTAL_FORMS": "3", "child-INITIAL_FORMS": "0"}


def make_ninja(guardian, name, **fields):
    """A ninja linked to `guardian` through a Guardianship."""
    ninja = Ninja.objects.create(name=name, **fields)
    Guardianship.objects.create(guardian=guardian, ninja=ninja)
    return ninja


class LoginViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.guardian.set_password(PASSWORD)
        cls.guardian.save()

    def test_get_renders_form(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_valid_login_by_email_redirects_to_account_page(self):
        response = self.client.post(reverse("login"), login_data(self.guardian.email, PASSWORD))
        self.assertRedirects(response, reverse("account_home"))

    def test_valid_login_by_username(self):
        """EmailOrUsernameBackend accepts either — seeded demo accounts are
        keyed by username."""
        response = self.client.post(reverse("login"), login_data(self.guardian.username, PASSWORD))
        self.assertRedirects(response, reverse("account_home"))

    def test_invalid_password_shows_error(self):
        response = self.client.post(reverse("login"), login_data(self.guardian.email, "wrong"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())

    def test_already_authenticated_redirects_away_from_form(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("login"))
        self.assertRedirects(response, reverse("account_home"))


class LogoutViewTests(TestCase):
    def test_logout_redirects_home_and_clears_session(self):
        guardian = User.objects.create(username="g1", email="g1@example.com")
        self.client.force_login(guardian)

        response = self.client.get(reverse("logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)


class PasswordResetMailTests(TestCase):
    """The reset mail goes through the mail engine like every mail: queued
    as account mail, in the account's language, with a working link."""

    def setUp(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("load_mail_templates", stdout=StringIO())
        self.user = User.objects.create(username="jan", email="jan@example.com", preferred_language="nl-be")
        self.user.set_password("an-old-password-77")
        self.user.save()

    def test_reset_is_queued_with_a_working_link(self):
        from mailing.models import EmailMessage

        response = self.client.post(reverse("password_reset"), {"email": "jan@example.com"})

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)
        queued = EmailMessage.objects.get(template_key="password_reset")
        self.assertEqual((queued.recipient, queued.category, queued.language), ("jan@example.com", "service", "nl-be"))
        link = next(line.strip() for line in queued.body.splitlines() if "/password-reset/confirm/" in line)
        self.assertEqual(self.client.get(link.replace("http://testserver", ""), follow=True).status_code, 200)

    def test_unknown_address_queues_nothing(self):
        from mailing.models import EmailMessage

        self.client.post(reverse("password_reset"), {"email": "nobody@example.com"})
        self.assertFalse(EmailMessage.objects.exists())


class ChangePasswordViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create(username="g1", email="g1@example.com", must_change_password=True)
        cls.guardian.set_password(PASSWORD)
        cls.guardian.save()

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("change_password"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_logged_in_get_renders_form(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("change_password"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["forced"])

    def test_valid_post_changes_password_and_clears_forced_flag(self):
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse("change_password"),
            {
                "old_password": PASSWORD,
                "new_password1": "a-brand-new-password-99",
                "new_password2": "a-brand-new-password-99",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.guardian.refresh_from_db()
        self.assertFalse(self.guardian.must_change_password)
        self.assertTrue(self.guardian.check_password("a-brand-new-password-99"))


class RegisterPagesTests(TestCase):
    def test_register_renders(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)

    def test_register_guardian_renders(self):
        response = self.client.get(reverse("register_guardian"))
        self.assertEqual(response.status_code, 200)


class GuardianDetailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.other_guardian = User.objects.create(username="g2", email="g2@example.com")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("account_home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_own_account_renders(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("account_home"))
        self.assertEqual(response.status_code, 200)

    def test_lists_only_own_ninjas(self):
        """The account page has no id in its URL — it always shows the
        logged-in account's own ninjas, never another family's."""
        mine = make_ninja(self.guardian, "Mine")
        make_ninja(self.other_guardian, "Theirs")
        self.client.force_login(self.guardian)

        response = self.client.get(reverse("account_home"))

        self.assertEqual([entry["child"] for entry in response.context["children"]], [mine])

    def test_ninja_login_is_sent_to_its_own_page(self):
        ninja_login = User.objects.create(username="kid", account_type=User.NINJA)
        ninja = make_ninja(self.guardian, "Kid", account=ninja_login)
        self.client.force_login(ninja_login)

        response = self.client.get(reverse("account_home"))

        self.assertRedirects(response, reverse("ninja_detail", kwargs={"ninja_id": ninja.id}))


class AddChildViewTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")

    def test_login_required(self):
        response = self.client.post(reverse("add_ninja"), {"consent": "on", "family_name": "Peeters", "name": "Kid"})
        self.assertEqual(response.status_code, 302)

    def test_the_consent_is_optional_and_recorded(self):
        from accounts.consent import CHILD_DATA_WORDING_VERSION

        self.client.force_login(self.guardian)
        self.client.post(
            reverse("add_ninja"), {"family_name": "Peeters", "name": "No Consent", "date_of_birth": _dob(10)}
        )
        guardianship = Guardianship.objects.get(ninja__name="No Consent")
        self.assertIsNone(guardianship.consent_given_at)

        self.client.post(
            reverse("add_ninja"),
            {"consent": "on", "family_name": "Peeters", "name": "Consented", "date_of_birth": _dob(10)},
        )
        guardianship = Guardianship.objects.get(ninja__name="Consented")
        self.assertIsNotNone(guardianship.consent_given_at)
        self.assertEqual(guardianship.consent_wording_version, CHILD_DATA_WORDING_VERSION)

    def test_the_form_asks_for_the_consent(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("account_home"))
        self.assertContains(response, 'name="consent">')
        self.assertContains(response, "Use my children's details")

    def test_post_creates_participant(self):
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse("add_ninja"),
            {"consent": "on", "family_name": "Peeters", "name": "New Kid", "date_of_birth": _dob(10)},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/partials/_children_list.html")
        self.assertTrue(Ninja.objects.of_guardian(self.guardian).filter(name="New Kid").exists())

    def test_without_javascript_it_goes_back_to_the_account_page(self):
        """No htmx (no JavaScript, or it didn't load): never the bare fragment."""
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse("add_ninja"),
            {"consent": "on", "family_name": "Peeters", "name": "No JS Kid", "date_of_birth": _dob(10)},
        )
        self.assertRedirects(response, reverse("account_home"))
        self.assertTrue(Ninja.objects.of_guardian(self.guardian).filter(name="No JS Kid").exists())
        self.assertRedirects(self.client.get(reverse("add_ninja")), reverse("account_home"))

    def test_without_javascript_errors_show_on_the_whole_account_page(self):
        self.client.force_login(self.guardian)
        response = self.client.post(reverse("add_ninja"), {"family_name": "Peeters", "name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/guardian_detail.html")
        self.assertContains(response, '<details class="cd-card add-child" id="add-child" open>')
        self.assertFalse(Ninja.objects.of_guardian(self.guardian).exists())

    def test_picked_icon_links_the_standard_avatar(self):
        self.client.force_login(self.guardian)
        self.client.post(
            reverse("add_ninja"),
            {
                "consent": "on",
                "family_name": "Peeters",
                "name": "A",
                "date_of_birth": _dob(10),
                "icon": "alien-01-green.svg",
            },
        )
        self.client.post(
            reverse("add_ninja"),
            {
                "consent": "on",
                "family_name": "Peeters",
                "name": "B",
                "date_of_birth": _dob(10),
                "icon": "alien-01-green.svg",
            },
        )
        photos = set(Ninja.objects.of_guardian(self.guardian).values_list("photo", flat=True))
        self.assertEqual(photos, {"library/ninjas/alien-01-green.svg"})
        self.assertFalse((self.media_root / "participants").exists())

    def test_unknown_icon_is_ignored(self):
        self.client.force_login(self.guardian)
        self.client.post(
            reverse("add_ninja"),
            {
                "consent": "on",
                "family_name": "Peeters",
                "name": "A",
                "date_of_birth": _dob(10),
                "icon": "../../settings.py",
            },
        )
        self.assertFalse(Ninja.objects.get(name="A").photo)

    def test_any_adult_account_can_add_children(self):
        """No separate "guardian" role any more — e.g. a dojo owner adds
        their own child from their account page directly."""
        owner = make_champion(username="owner1")
        self.client.force_login(owner)
        self.client.post(reverse("add_ninja"), {"consent": "on", "family_name": "Peeters", "name": "Owner Kid"})
        self.assertEqual(list(Ninja.objects.of_guardian(owner).values_list("name", flat=True)), ["Owner Kid"])

    def test_ninja_login_cannot_add_children(self):
        ninja_login = User.objects.create(username="kid", account_type=User.NINJA)
        self.client.force_login(ninja_login)
        response = self.client.post(reverse("add_ninja"), {"consent": "on", "family_name": "Peeters", "name": "Nope"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Ninja.objects.exists())

    def test_blank_name_creates_nothing(self):
        self.client.force_login(self.guardian)
        self.client.post(reverse("add_ninja"), {"consent": "on", "family_name": "Peeters", "name": "  "})
        self.assertEqual(Ninja.objects.of_guardian(self.guardian).count(), 0)

    def test_gender_is_saved_and_optional(self):
        self.client.force_login(self.guardian)
        self.client.post(
            reverse("add_ninja"), {"consent": "on", "family_name": "Peeters", "name": "A", "gender": Ninja.GIRL}
        )
        self.client.post(reverse("add_ninja"), {"consent": "on", "family_name": "Peeters", "name": "B"})
        self.client.post(
            reverse("add_ninja"), {"consent": "on", "family_name": "Peeters", "name": "C", "gender": "dragon"}
        )
        genders = dict(Ninja.objects.of_guardian(self.guardian).values_list("name", "gender"))
        self.assertEqual(genders, {"A": Ninja.GIRL, "B": Ninja.UNSPECIFIED, "C": Ninja.UNSPECIFIED})


class ChildDetailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.other_guardian = User.objects.create(username="g2", email="g2@example.com")
        cls.child = make_ninja(cls.guardian, "Kid One")
        cls.other_child = make_ninja(cls.other_guardian, "Kid Two")

    def test_own_child_renders(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": self.child.id}))
        self.assertEqual(response.status_code, 200)

    def test_another_familys_child_is_404(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": self.other_child.id}))
        self.assertEqual(response.status_code, 404)

    def test_second_guardian_can_see_the_ninja_too(self):
        """A ninja can have more than one parent/guardian."""
        Guardianship.objects.create(guardian=self.other_guardian, ninja=self.child)
        self.client.force_login(self.other_guardian)
        response = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": self.child.id}))
        self.assertEqual(response.status_code, 200)

    def test_ninja_can_see_own_page_but_not_edit_it(self):
        ninja_login = User.objects.create(username="kid", account_type=User.NINJA)
        self.child.account = ninja_login
        self.child.save(update_fields=["account"])
        self.client.force_login(ninja_login)

        page = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": self.child.id}))
        edit = self.client.get(reverse("edit_ninja", kwargs={"ninja_id": self.child.id}))
        other = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": self.other_child.id}))

        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context["can_edit"])
        self.assertEqual(edit.status_code, 404)
        self.assertEqual(other.status_code, 404)


class EditChildViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.child = make_ninja(cls.guardian, "Kid One")

    def test_get_returns_edit_form_partial(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("edit_ninja", kwargs={"ninja_id": self.child.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/partials/_child_header_edit.html")

    def test_post_updates_name(self):
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse("edit_ninja", kwargs={"ninja_id": self.child.id}),
            {"name": "Renamed Kid", "date_of_birth": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/partials/_child_header_display.html")
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "Renamed Kid")

    def test_post_updates_gender_and_keeps_it_when_not_sent(self):
        self.client.force_login(self.guardian)
        url = reverse("edit_ninja", kwargs={"ninja_id": self.child.id})
        self.client.post(url, {"name": "Kid One", "date_of_birth": "", "gender": Ninja.GIRL})
        self.child.refresh_from_db()
        self.assertEqual(self.child.gender, Ninja.GIRL)

        self.client.post(url, {"name": "Kid One", "date_of_birth": ""})
        self.child.refresh_from_db()
        self.assertEqual(self.child.gender, Ninja.GIRL)

    def test_an_uploaded_photo_is_kept_unless_an_avatar_is_picked(self):
        Ninja.objects.filter(pk=self.child.pk).update(photo="participants/own-photo.jpg")
        self.client.force_login(self.guardian)
        url = reverse("edit_ninja", kwargs={"ninja_id": self.child.id})
        self.assertContains(
            self.client.get(url), '<option value="" selected>Keep the current photo</option>', html=True
        )

        self.client.post(url, {"name": "Kid One", "icon": ""})
        self.child.refresh_from_db()
        self.assertEqual(self.child.photo.name, "participants/own-photo.jpg")

    def test_a_child_without_a_photo_keeps_none_unless_an_avatar_is_picked(self):
        self.client.force_login(self.guardian)
        url = reverse("edit_ninja", kwargs={"ninja_id": self.child.id})
        self.assertContains(self.client.get(url), '<option value="" selected>No avatar</option>', html=True)
        self.client.post(url, {"name": "Kid One", "icon": ""})
        self.child.refresh_from_db()
        self.assertFalse(self.child.photo)

    def test_edit_form_preselects_the_gender(self):
        Ninja.objects.filter(pk=self.child.pk).update(gender=Ninja.OTHER)
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("edit_ninja", kwargs={"ninja_id": self.child.id}))
        self.assertContains(response, '<option value="other" selected>')


class EditAccountViewTests(TestCase):
    """The account page's own details (accounts.views.edit_account): the same
    click-to-edit over htmx as a child's header. The email address is shown,
    never edited here."""

    HTMX = {"HTTP_HX_REQUEST": "true"}

    @classmethod
    def setUpTestData(cls):
        Municipality.objects.create(postal_code="9000", name="Gent", center=Point(3.7174, 51.0543, srid=4326))
        cls.guardian = User.objects.create(
            username="g1", email="g1@example.com", first_name="Jane", last_name="Doe", phone="0470 11 22 33"
        )
        cls.other = User.objects.create(username="g2", email="g2@example.com", first_name="Other")

    def post(self, data, **extra):
        return self.client.post(
            reverse("edit_account"),
            {"first_name": "Janet", "last_name": "Peeters", "phone": "", "postal_code": "9000", **data},
            **extra,
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("edit_account"), **self.HTMX)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_a_ninja_login_gets_a_404(self):
        ninja_login = User.objects.create(username="kid", account_type=User.NINJA)
        make_ninja(self.guardian, "Kid", account=ninja_login)
        self.client.force_login(ninja_login)
        self.assertEqual(self.client.get(reverse("edit_account"), **self.HTMX).status_code, 404)
        self.assertEqual(self.post({}, **self.HTMX).status_code, 404)

    def test_the_account_page_shows_the_details_with_an_edit_link(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("account_home"))
        self.assertTemplateUsed(response, "accounts/partials/_account_details_display.html")
        self.assertContains(response, "g1@example.com")
        self.assertContains(response, "0470 11 22 33")
        self.assertContains(response, f'hx-get="{reverse("edit_account")}"')

    def test_get_returns_the_form_with_the_email_read_only(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("edit_account"), **self.HTMX)
        self.assertTemplateUsed(response, "accounts/partials/_account_details_edit.html")
        self.assertTemplateNotUsed(response, "accounts/guardian_detail.html")
        self.assertContains(response, 'value="Jane"')
        self.assertContains(response, "g1@example.com")
        self.assertNotContains(response, 'name="email"')

    def test_post_saves_the_details_and_swaps_back(self):
        self.client.force_login(self.guardian)
        response = self.post({"phone": "+32 470 99 88 77"}, **self.HTMX)
        self.assertTemplateUsed(response, "accounts/partials/_account_details_display.html")
        self.assertContains(response, "Welcome back, Janet")
        self.guardian.refresh_from_db()
        self.assertEqual(
            (self.guardian.first_name, self.guardian.last_name, self.guardian.phone, self.guardian.postal_code),
            ("Janet", "Peeters", "+32 470 99 88 77", "9000"),
        )
        self.other.refresh_from_db()
        self.assertEqual(self.other.first_name, "Other")

    def test_a_posted_email_is_ignored(self):
        self.client.force_login(self.guardian)
        self.post({"email": "someone-else@example.com"}, **self.HTMX)
        self.guardian.refresh_from_db()
        self.assertEqual(self.guardian.email, "g1@example.com")

    def test_an_unknown_postcode_or_no_first_name_saves_nothing(self):
        self.client.force_login(self.guardian)
        for data, field in (({"postal_code": "0001"}, "postal_code"), ({"first_name": ""}, "first_name")):
            response = self.post(data, **self.HTMX)
            self.assertTemplateUsed(response, "accounts/partials/_account_details_edit.html")
            self.assertIn(field, response.context["form"].errors)
        self.guardian.refresh_from_db()
        self.assertEqual((self.guardian.first_name, self.guardian.postal_code), ("Jane", ""))

    def test_without_htmx_it_uses_the_account_page(self):
        self.client.force_login(self.guardian)
        page = self.client.get(reverse("edit_account"))
        self.assertTemplateUsed(page, "accounts/guardian_detail.html")
        self.assertTemplateUsed(page, "accounts/partials/_account_details_edit.html")

        invalid = self.post({"postal_code": "0001"})
        self.assertTemplateUsed(invalid, "accounts/guardian_detail.html")
        self.assertContains(invalid, "That isn&#x27;t a Belgian postcode we know.")

        self.assertRedirects(self.post({}), reverse("account_home"))
        self.guardian.refresh_from_db()
        self.assertEqual(self.guardian.first_name, "Janet")

    def test_the_change_is_in_the_audit_log(self):
        from auditlog.models import LogEntry

        self.client.force_login(self.guardian)
        self.post({}, **self.HTMX)
        entry = LogEntry.objects.get_for_object(self.guardian).latest("pk")
        self.assertEqual(entry.actor, self.guardian)
        self.assertEqual(entry.changes_dict["first_name"], ["Jane", "Janet"])


class EmailChangeTests(TestCase):
    """Changing the account's own email address (accounts.email_change,
    DATA_MODEL.md §22): asked with the password, confirmed from a link sent
    to the new address, the old address told, other sessions ended."""

    def setUp(self):
        from io import StringIO

        from django.core.cache import cache
        from django.core.management import call_command

        cache.clear()  # the test cache (db 3): the one-request-a-minute throttle
        call_command("load_mail_templates", stdout=StringIO())
        self.user = User.objects.create(username="jan", email="jan@example.com", first_name="Jan")
        self.user.set_password(PASSWORD)
        self.user.save()

    def ask(self, new_email="jan.new@example.com", password=PASSWORD):
        return self.client.post(reverse("change_email"), {"new_email": new_email, "password": password})

    def confirm_path(self):
        import re
        from urllib.parse import urlparse

        from mailing.models import EmailMessage

        body = EmailMessage.objects.get(template_key="email_change_confirm").body
        return urlparse(re.search(r"\S+/account/email/confirm/\S+", body).group(0)).path

    def test_login_required_and_not_for_a_ninja_login(self):
        self.assertEqual(self.client.get(reverse("change_email")).status_code, 302)
        ninja_login = User.objects.create(username="kid", email="kid@example.com", account_type=User.NINJA)
        make_ninja(self.user, "Kid", account=ninja_login)
        self.client.force_login(ninja_login)
        self.assertEqual(self.client.get(reverse("change_email")).status_code, 404)

    def test_asking_mails_a_link_to_the_new_address_and_changes_nothing_yet(self):
        from mailing.models import EmailMessage

        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("change_email")), "jan@example.com")
        response = self.ask()
        self.assertRedirects(response, reverse("account_home"))
        queued = EmailMessage.objects.get()
        self.assertEqual(
            (queued.template_key, queued.recipient, queued.category, queued.user),
            ("email_change_confirm", "jan.new@example.com", "service", self.user),
        )
        self.assertIn("You asked to change", queued.body)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "jan@example.com")

    def test_the_password_is_needed(self):
        from mailing.models import EmailMessage

        self.client.force_login(self.user)
        response = self.ask(password="wrong")
        self.assertIn("password", response.context["form"].errors)
        self.assertFalse(EmailMessage.objects.exists())

    def test_a_taken_or_blocked_or_same_address_is_refused(self):
        from mailing.models import EmailMessage, EmailSuppression

        User.objects.create(username="other", email="Taken@Example.com")
        EmailSuppression.objects.create(email="bounced@example.com")
        self.client.force_login(self.user)
        for address in ("taken@example.com", "bounced@example.com", "JAN@example.com"):
            self.assertIn("new_email", self.ask(address).context["form"].errors, address)
        self.assertFalse(EmailMessage.objects.exists())

    def test_one_request_a_minute(self):
        self.client.force_login(self.user)
        self.ask()
        response = self.ask("jan.other@example.com")
        self.assertContains(response, "Please wait a minute")

    def test_confirming_changes_it_tells_the_old_address_and_ends_other_sessions(self):
        from django.test import Client

        from mailing.models import EmailMessage

        elsewhere = Client()
        elsewhere.force_login(self.user)
        self.client.force_login(self.user)
        self.ask()
        path = self.confirm_path()

        page = self.client.get(path)
        self.assertContains(page, "jan.new@example.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "jan@example.com")  # a GET (a mail scanner) changes nothing

        response = self.client.post(path)
        self.assertRedirects(response, reverse("account_home"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "jan.new@example.com")
        notice = EmailMessage.objects.get(template_key="email_changed")
        self.assertEqual(notice.recipient, "jan@example.com")
        self.assertIn("jan.new@example.com", notice.body)
        self.assertEqual(self.client.get(reverse("account_home")).status_code, 200)  # this session stays
        self.assertEqual(elsewhere.get(reverse("account_home")).status_code, 302)  # the other one ended

    def test_the_link_works_once(self):
        self.client.force_login(self.user)
        self.ask()
        path = self.confirm_path()
        self.client.post(path)
        response = self.client.post(path)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "already been used", status_code=400)

    def test_the_link_expires(self):
        import time

        self.client.force_login(self.user)
        self.ask()
        path = self.confirm_path()
        with patch("django.core.signing.time.time", return_value=time.time() + 25 * 3600):
            response = self.client.post(path)
        self.assertContains(response, "expired", status_code=400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "jan@example.com")

    def test_logged_out_the_family_logs_in_first_and_another_account_gets_a_404(self):
        self.client.force_login(self.user)
        self.ask()
        path = self.confirm_path()
        self.client.logout()
        response = self.client.get(path)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertIn("next=", response.url)

        self.client.force_login(User.objects.create(username="someone", email="someone@example.com"))
        self.assertEqual(self.client.post(path).status_code, 404)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "jan@example.com")

    def test_an_address_taken_meanwhile_is_refused_at_confirmation(self):
        self.client.force_login(self.user)
        self.ask()
        path = self.confirm_path()
        User.objects.create(username="quick", email="jan.new@example.com")
        self.assertContains(self.client.post(path), "already exists", status_code=400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "jan@example.com")

    def test_open_password_reset_links_stop_working(self):
        from django.contrib.auth.tokens import default_token_generator

        token = default_token_generator.make_token(self.user)
        self.client.force_login(self.user)
        self.ask()
        self.client.post(self.confirm_path())
        self.user.refresh_from_db()
        self.assertFalse(default_token_generator.check_token(self.user, token))

    def test_the_change_is_in_the_audit_log(self):
        from auditlog.models import LogEntry

        self.client.force_login(self.user)
        self.ask()
        self.client.post(self.confirm_path())
        entry = LogEntry.objects.get_for_object(self.user).latest("pk")
        self.assertEqual(entry.actor, self.user)
        self.assertEqual(entry.changes_dict["email"], ["jan@example.com", "jan.new@example.com"])

    def test_a_new_address_set_anywhere_ends_the_account_sessions(self):
        """The session check covers the email (User._get_session_auth_hash),
        also for a change made in the Django admin."""
        self.client.force_login(self.user)
        User.objects.filter(pk=self.user.pk).update(email="changed@example.com")
        self.assertEqual(self.client.get(reverse("account_home")).status_code, 302)

    def test_the_details_form_links_to_it(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("edit_account"), HTTP_HX_REQUEST="true")
        self.assertContains(response, reverse("change_email"))


class ChildAvatarTests(TempMediaMixin, TestCase):
    """A child's own login picks its avatar (accounts.views.ninja_avatar):
    only the standard avatars; uploading a photo stays the guardian's."""

    def setUp(self):
        super().setUp()
        self.guardian = User.objects.create(username="g1", email="g1@example.com")
        self.login = User.objects.create(username="kid", email="kid@example.com", account_type=User.NINJA)
        self.child = make_ninja(self.guardian, "Emma", account=self.login)
        self.url = reverse("ninja_avatar", kwargs={"ninja_id": self.child.id})

    def test_the_child_page_offers_it_to_the_child_only(self):
        detail = reverse("ninja_detail", kwargs={"ninja_id": self.child.id})
        self.client.force_login(self.login)
        self.assertContains(self.client.get(detail), f'hx-get="{self.url}"')
        self.client.force_login(self.guardian)
        self.assertNotContains(self.client.get(detail), f'hx-get="{self.url}"')

    def test_the_picker_offers_the_standard_avatars_and_no_upload(self):
        from .template_avatars import TEMPLATE_KID_AVATARS

        self.client.force_login(self.login)
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(response, "accounts/partials/_child_avatar_picker.html")
        self.assertContains(response, 'type="radio"', count=len(TEMPLATE_KID_AVATARS))
        self.assertNotContains(response, 'type="file"')

    def test_picking_one_links_the_standard_avatar(self):
        from .template_avatars import TEMPLATE_KID_AVATARS

        filename = TEMPLATE_KID_AVATARS[1][0]
        self.client.force_login(self.login)
        response = self.client.post(self.url, {"icon": filename})
        self.assertTemplateUsed(response, "accounts/partials/_child_header_display.html")
        self.child.refresh_from_db()
        self.assertEqual(self.child.photo.name, f"library/ninjas/{filename}")

    def test_a_standard_avatar_is_linked_never_copied(self):
        """Every child who picks the same avatar shares the one library file
        (core.image_library); nothing lands in the per-child upload folder."""
        from pathlib import Path

        from django.conf import settings

        from .template_avatars import TEMPLATE_KID_AVATARS

        filename = TEMPLATE_KID_AVATARS[0][0]
        other_login = User.objects.create(username="kid2", email="kid2@example.com", account_type=User.NINJA)
        other = make_ninja(self.guardian, "Mats", account=other_login)
        for login, child in ((self.login, self.child), (other_login, other)):
            self.client.force_login(login)
            self.client.post(reverse("ninja_avatar", kwargs={"ninja_id": child.id}), {"icon": filename})
        self.child.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.child.photo.name, other.photo.name)
        self.assertEqual(self.child.photo.name, f"library/ninjas/{filename}")
        self.assertEqual(
            list((Path(settings.MEDIA_ROOT) / "library" / "ninjas").iterdir()),
            [Path(settings.MEDIA_ROOT) / "library" / "ninjas" / filename],
        )
        self.assertFalse((Path(settings.MEDIA_ROOT) / "participants").exists())

    def test_an_upload_or_an_unknown_choice_changes_nothing(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        Ninja.objects.filter(pk=self.child.pk).update(photo="participants/from-the-guardian.jpg")
        self.client.force_login(self.login)
        upload = SimpleUploadedFile("me.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        response = self.client.post(self.url, {"icon": "../../etc/passwd", "photo": upload})
        self.assertTrue(response.context["form"].errors)
        self.client.post(self.url, {"photo": upload})
        self.child.refresh_from_db()
        self.assertEqual(self.child.photo.name, "participants/from-the-guardian.jpg")

    def test_another_ninja_login_gets_a_404(self):
        other_login = User.objects.create(username="kid2", email="kid2@example.com", account_type=User.NINJA)
        make_ninja(User.objects.create(username="g2", email="g2@example.com"), "Mats", account=other_login)
        self.client.force_login(other_login)
        self.assertEqual(self.client.get(self.url).status_code, 404)


class BadgeWidgetViewTests(TestCase):
    def test_login_required(self):
        guardian = User.objects.create(username="g1", email="g1@example.com")
        child = make_ninja(guardian, "Kid")
        response = self.client.get(reverse("ninja_badges", kwargs={"ninja_id": child.id}))
        self.assertEqual(response.status_code, 302)

    def test_renders_for_owning_guardian(self):
        guardian = User.objects.create(username="g1", email="g1@example.com")
        child = make_ninja(guardian, "Kid")
        self.client.force_login(guardian)
        response = self.client.get(reverse("ninja_badges", kwargs={"ninja_id": child.id}))
        self.assertEqual(response.status_code, 200)


class CancelRegistrationViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.child = make_ninja(cls.guardian, "Kid One")
        cls.waitlisted_child = make_ninja(cls.guardian, "Kid Two")
        dojo = Dojo.objects.create(name="Ghent")
        cls.event = Event.objects.create(
            name="Session",
            dojo=dojo,
            start_time="2030-01-01T10:00:00Z",
            end_time="2030-01-01T12:00:00Z",
            places=1,
        )
        cls.confirmed = Registration.objects.create(
            event=cls.event,
            ninja=cls.child,
            waiting_list=False,
            position=1,
        )
        cls.waitlisted = Registration.objects.create(
            event=cls.event,
            ninja=cls.waitlisted_child,
            waiting_list=True,
            position=2,
        )

    def test_cancelling_a_confirmed_spot_promotes_next_in_line(self):
        self.client.force_login(self.guardian)
        response = self.client.post(reverse("cancel_registration", kwargs={"registration_id": self.confirmed.id}))
        self.assertRedirects(response, reverse("account_home"))
        self.assertFalse(Registration.objects.filter(id=self.confirmed.id).exists())
        self.waitlisted.refresh_from_db()
        self.assertFalse(self.waitlisted.waiting_list)

    def test_cannot_cancel_another_familys_registration(self):
        other_guardian = User.objects.create(username="g2", email="g2@example.com")
        self.client.force_login(other_guardian)
        response = self.client.post(reverse("cancel_registration", kwargs={"registration_id": self.confirmed.id}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Registration.objects.filter(id=self.confirmed.id).exists())

    def test_promotion_notifies_the_dojo_team(self):
        """The waitlist-promotion side of this view (see setUpTestData's
        event/dojo) reuses a dojo with no team — build one with a champion,
        a mentor and a youth mentor here to check who gets notified: the
        people running the dojo, never a youth mentor."""
        owner = make_champion(username="owner1", email="owner@example.com")
        mentor = make_mentor(username="mentor1")
        youth = User.objects.create(username="kid", account_type=User.NINJA)
        dojo = make_dojo("Antwerp", champion=owner)
        add_member(dojo, mentor)
        add_member(dojo, youth, DojoMembership.YOUTH_MENTOR)
        event = Event.objects.create(
            name="Antwerp Session",
            dojo=dojo,
            start_time="2030-01-01T10:00:00Z",
            end_time="2030-01-01T12:00:00Z",
            places=1,
        )
        confirmed = Registration.objects.create(event=event, ninja=self.child, waiting_list=False, position=1)
        Registration.objects.create(event=event, ninja=self.waitlisted_child, waiting_list=True, position=2)
        self.client.force_login(self.guardian)

        with patch("dojos.team.notify") as mock_notify:
            self.client.post(reverse("cancel_registration", kwargs={"registration_id": confirmed.id}))

        recipient_ids = {call.args[0].pk for call in mock_notify.call_args_list}
        self.assertEqual(recipient_ids, {owner.pk, mentor.pk})
        args, kwargs = mock_notify.call_args
        self.assertIn("A spot opened up in", str(args[1]))
        self.assertEqual(kwargs["params"], {"event": "Antwerp Session"})
        self.assertEqual(kwargs["dojo"], dojo)

    def test_no_notification_when_dojo_has_no_team(self):
        """setUpTestData's dojo has nobody on its team — promoting from its
        waitlist notifies no one (and doesn't fail)."""
        self.client.force_login(self.guardian)
        with patch("dojos.team.notify") as mock_notify:
            self.client.post(
                reverse(
                    "cancel_registration",
                    kwargs={"registration_id": self.confirmed.id},
                )
            )
        mock_notify.assert_not_called()


class RegisterGuardianViewTests(TestCase):
    valid_password = "a-brand-new-password-99"

    def _valid_post_data(self, **overrides):
        data = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "",
            "password": self.valid_password,
            "consent": "on",
            **CHILD_ROWS,
            "child-0-name": "Sam",
            "child-0-family_name": "Peeters",
            "child-0-date_of_birth": _dob(10),
            "child-0-allergies_notes": "",
        }
        data.update(overrides)
        return data

    def test_sign_up_records_the_consent_for_the_children(self):
        from accounts.consent import CHILD_DATA_WORDING_VERSION

        self.assertContains(self.client.get(reverse("register_guardian")), "Use my children's details")
        self.client.post(reverse("register_guardian"), self._valid_post_data(child_data_mail="on"))
        guardianship = Guardianship.objects.get(guardian__email="jane@example.com")
        self.assertIsNotNone(guardianship.consent_given_at)
        self.assertEqual(guardianship.consent_wording_version, CHILD_DATA_WORDING_VERSION)

    def test_sign_up_without_the_consent_for_the_children(self):
        response = self.client.post(reverse("register_guardian"), self._valid_post_data())
        self.assertRedirects(response, reverse("account_home"))
        self.assertIsNone(Guardianship.objects.get(guardian__email="jane@example.com").consent_given_at)

    def test_get_renders_one_empty_child_row(self):
        response = self.client.get(reverse("register_guardian"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["children"].forms), 1)

    def test_valid_post_creates_account_logs_in_and_redirects(self):
        response = self.client.post(reverse("register_guardian"), self._valid_post_data())

        guardian = User.objects.get(email="jane@example.com")
        self.assertRedirects(response, reverse("account_home"))
        self.assertTrue(guardian.check_password(self.valid_password))
        self.assertEqual(guardian.first_name, "Jane")
        self.assertEqual(guardian.last_name, "Doe")
        self.assertEqual(list(Ninja.objects.of_guardian(guardian).values_list("name", flat=True)), ["Sam"])
        self.assertEqual(int(self.client.session["_auth_user_id"]), guardian.id)

    def test_valid_post_with_non_contiguous_child_indices_creates_both(self):
        """Simulates a family who added a 2nd/3rd child then removed the
        middle one client-side, leaving gaps in the field numbering."""
        data = self._valid_post_data(
            **{
                "child-2-name": "Alex",
                "child-2-family_name": "Doe",
                "child-2-date_of_birth": _dob(12),
                "child-2-allergies_notes": "Peanut allergy",
            },
        )
        self.client.post(reverse("register_guardian"), data)

        guardian = User.objects.get(email="jane@example.com")
        self.assertEqual(Ninja.objects.of_guardian(guardian).count(), 2)
        alex = Ninja.objects.of_guardian(guardian).get(name="Alex")
        self.assertEqual(alex.allergies_notes, "Peanut allergy")

    def test_newsletter_is_opt_in_and_logged(self):
        from mailing.categories import MailCategory
        from mailing.models import ConsentEvent
        from mailing.preferences import is_subscribed

        self.client.post(reverse("register_guardian"), self._valid_post_data())
        without = User.objects.get(email="jane@example.com")
        self.assertFalse(is_subscribed(without, MailCategory.NEWSLETTER))
        self.assertFalse(ConsentEvent.objects.exists())

        self.client.logout()
        self.client.post(reverse("register_guardian"), self._valid_post_data(email="joe@example.com", newsletter="on"))
        with_newsletter = User.objects.get(email="joe@example.com")
        self.assertTrue(is_subscribed(with_newsletter, MailCategory.NEWSLETTER))
        self.assertEqual(ConsentEvent.objects.get().source, ConsentEvent.SIGNUP)

    def test_form_shows_the_privacy_explanation(self):
        self.assertContains(self.client.get(reverse("register_guardian")), "We use what we know about your family")

    def test_child_gender_is_saved_per_row(self):
        data = self._valid_post_data(
            **{
                "child-0-gender": Ninja.GIRL,
                "child-1-name": "Alex",
                "child-1-family_name": "Doe",
                "child-1-date_of_birth": _dob(9),
            }
        )
        self.client.post(reverse("register_guardian"), data)

        guardian = User.objects.get(email="jane@example.com")
        genders = dict(Ninja.objects.of_guardian(guardian).values_list("name", "gender"))
        self.assertEqual(genders, {"Sam": Ninja.GIRL, "Alex": Ninja.UNSPECIFIED})

    def test_form_offers_the_gender_choices(self):
        response = self.client.get(reverse("register_guardian"))
        self.assertContains(response, 'name="child-0-gender"')
        self.assertContains(response, '<option value="unspecified" selected>')

    def test_postcode_and_mail_language_are_saved(self):
        Municipality.objects.create(postal_code="9000", name="Gent", center=Point(3.7174, 51.0543, srid=4326))
        self.client.post(
            reverse("register_guardian"), self._valid_post_data(postal_code="9000", preferred_language="fr-be")
        )

        guardian = User.objects.get(email="jane@example.com")
        self.assertEqual((guardian.postal_code, guardian.preferred_language), ("9000", "fr-be"))

    def test_postcode_is_optional_and_language_defaults_to_the_page_language(self):
        self.client.post(reverse("register_guardian"), self._valid_post_data(), HTTP_ACCEPT_LANGUAGE="nl-be")

        guardian = User.objects.get(email="jane@example.com")
        self.assertEqual((guardian.postal_code, guardian.preferred_language), ("", "nl-be"))

    def test_unknown_postcode_is_rejected(self):
        response = self.client.post(reverse("register_guardian"), self._valid_post_data(postal_code="0000"))

        self.assertFalse(User.objects.filter(email="jane@example.com").exists())
        self.assertTrue(response.context["form"].errors.get("postal_code"))

    def test_duplicate_email_is_rejected(self):
        User.objects.create(username="existing", email="jane@example.com")

        response = self.client.post(reverse("register_guardian"), self._valid_post_data())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("email"))
        self.assertEqual(User.objects.filter(email="jane@example.com").count(), 1)

    def test_weak_password_is_rejected(self):
        response = self.client.post(reverse("register_guardian"), self._valid_post_data(password="password"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("password"))
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_missing_consent_is_rejected(self):
        response = self.client.post(reverse("register_guardian"), self._valid_post_data(consent=""))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("consent"))
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_child_missing_required_fields_is_rejected(self):
        response = self.client.post(
            reverse("register_guardian"), self._valid_post_data(**{"child-0-name": "", "child-0-date_of_birth": ""})
        )

        self.assertEqual(response.status_code, 200)
        row = response.context["children"].forms[0]
        self.assertIn("name", row.errors)
        self.assertIn("date_of_birth", row.errors)
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())
        self.assertFalse(Ninja.objects.exists())

    def test_no_children_is_rejected(self):
        data = self._valid_post_data()
        for key in ["child-0-name", "child-0-family_name", "child-0-date_of_birth", "child-0-allergies_notes"]:
            del data[key]

        response = self.client.post(reverse("register_guardian"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["children"].non_form_errors(), ["Add at least one child."])
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_returns_to_the_event_sign_up_it_came_from(self):
        """Signing up a child for a session as a visitor: event_signup's
        login wall → Create an account → family sign-up → back there."""
        next_url = "/events/7/signup/"
        page = self.client.get(reverse("register_guardian"), {"next": next_url})
        self.assertContains(page, f'name="next" value="{next_url}"')

        response = self.client.post(reverse("register_guardian"), self._valid_post_data(next=next_url))
        self.assertRedirects(response, next_url, fetch_redirect_response=False)

    def test_never_returns_to_another_site(self):
        response = self.client.post(
            reverse("register_guardian"), self._valid_post_data(next="https://evil.example.com/")
        )
        self.assertRedirects(response, reverse("account_home"))


class RegisterIndividualViewTests(TestCase):
    """Sign-up without children, for someone who wants to start a dojo or
    volunteer: the account first, then on to the application."""

    valid_password = "a-brand-new-password-99"

    def _valid_post_data(self, **overrides):
        return {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "",
            "password": self.valid_password,
            **overrides,
        }

    def test_creates_an_account_without_children_and_logs_in(self):
        response = self.client.post(reverse("register_individual"), self._valid_post_data())

        jane = User.objects.get(email="jane@example.com")
        self.assertRedirects(response, reverse("account_home"))
        self.assertEqual((jane.first_name, jane.last_name, jane.account_type), ("Jane", "Doe", User.ADULT))
        self.assertTrue(jane.check_password(self.valid_password))
        self.assertFalse(Ninja.objects.of_guardian(jane).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), jane.id)

    def test_goes_straight_on_to_the_application(self):
        for name in ("register_dojo", "register_helper"):
            with self.subTest(name):
                self.client.logout()
                next_url = reverse(name)
                page = self.client.get(reverse("register_individual"), {"next": next_url})
                self.assertContains(page, f'name="next" value="{next_url}"')
                response = self.client.post(
                    reverse("register_individual"),
                    self._valid_post_data(email=f"{name}@example.com", next=next_url),
                )
                self.assertRedirects(response, next_url)

    def test_never_returns_to_another_site(self):
        response = self.client.post(
            reverse("register_individual"), self._valid_post_data(next="https://evil.example.com/")
        )
        self.assertRedirects(response, reverse("account_home"))

    def test_duplicate_email_is_rejected(self):
        User.objects.create(username="existing", email="jane@example.com")
        response = self.client.post(reverse("register_individual"), self._valid_post_data())
        self.assertTrue(response.context["form"].errors.get("email"))
        self.assertEqual(User.objects.filter(email="jane@example.com").count(), 1)

    def test_weak_password_is_rejected(self):
        response = self.client.post(reverse("register_individual"), self._valid_post_data(password="password"))
        self.assertTrue(response.context["form"].errors.get("password"))
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_newsletter_is_opt_in(self):
        from mailing.categories import MailCategory
        from mailing.preferences import is_subscribed

        self.client.post(reverse("register_individual"), self._valid_post_data(newsletter="on"))
        self.assertTrue(is_subscribed(User.objects.get(email="jane@example.com"), MailCategory.NEWSLETTER))

    def test_logged_in_account_is_sent_to_account_page(self):
        self.client.force_login(User.objects.create(username="someone", email="someone@example.com"))
        self.assertRedirects(self.client.get(reverse("register_individual")), reverse("account_home"))

    @override_settings(HELP_CENTRE_URL="/docs/")
    def test_links_to_the_help_centre_page_in_the_visitors_language(self):
        dojo = self.client.get(reverse("register_individual"), {"next": reverse("register_dojo")})
        self.assertContains(dojo, 'href="/docs/volunteering/start-a-new-dojo.html"')
        self.assertNotContains(dojo, "become-a-mentor-or-volunteer.html")

        mentor = self.client.get(
            reverse("register_individual"), {"next": reverse("register_helper")}, HTTP_ACCEPT_LANGUAGE="nl-be"
        )
        self.assertContains(mentor, 'href="/docs/nl/volunteering/become-a-mentor-or-volunteer.html"')

        both = self.client.get(reverse("register_individual"), HTTP_ACCEPT_LANGUAGE="fr-be")
        self.assertContains(both, 'href="/docs/fr/volunteering/start-a-new-dojo.html"')
        self.assertContains(both, 'href="/docs/fr/volunteering/become-a-mentor-or-volunteer.html"')


class RegisterChooserTests(TestCase):
    """The "Get involved" chooser: a visitor without an account who wants to
    start a dojo or volunteer gets the sign-up without children, and a login
    wall's `next` is carried into family sign-up."""

    def test_visitor_cards_lead_to_sign_up_then_the_application(self):
        response = self.client.get(reverse("register"))
        for name in ("register_dojo", "register_helper"):
            self.assertContains(response, f"{reverse('register_individual')}?next={reverse(name)}")

    def test_logged_in_cards_go_straight_to_the_application(self):
        self.client.force_login(User.objects.create(username="someone", email="someone@example.com"))
        response = self.client.get(reverse("register"))
        self.assertContains(response, f'href="{reverse("register_dojo")}"')
        self.assertNotContains(response, reverse("register_individual"))

    def test_family_card_carries_the_login_walls_next(self):
        response = self.client.get(reverse("register"), {"next": "/events/7/signup/"})
        self.assertContains(response, f"{reverse('register_guardian')}?next=/events/7/signup/")

    def test_login_page_carries_next_to_create_an_account(self):
        response = self.client.get(reverse("login"), {"next": "/events/7/signup/"})
        self.assertContains(response, f"{reverse('register')}?next=/events/7/signup/")


class RegisterGuardianWhenLoggedInTests(TestCase):
    """Family sign-up is only for people without an account: a logged-in
    account (any kind) adds its children from its account page instead —
    there's no separate guardian role to attach any more."""

    def test_logged_in_account_is_sent_to_account_page(self):
        owner = make_champion(username="owner1", email="owner@example.com")
        self.client.force_login(owner)
        response = self.client.get(reverse("register_guardian"))
        self.assertRedirects(response, reverse("account_home"))


class UniqueUsernameTests(TestCase):
    def test_returns_base_when_free(self):
        self.assertEqual(unique_username("jane-doe"), "jane-doe")

    def test_appends_suffix_on_collision(self):
        User.objects.create(username="jane-doe")
        self.assertEqual(unique_username("jane-doe"), "jane-doe2")

    def test_keeps_incrementing_past_multiple_collisions(self):
        User.objects.create(username="jane-doe")
        User.objects.create(username="jane-doe2")
        self.assertEqual(unique_username("jane-doe"), "jane-doe3")

    def test_falls_back_to_user_for_blank_base(self):
        self.assertEqual(unique_username(""), "user")


class BackgroundCheckValidPropertyTests(TestCase):
    """User.background_check_valid: a validated check that hasn't expired —
    what champion/mentor dojo access needs (dojos.access)."""

    def _user(self, **fields):
        return User.objects.create(username="u1", **fields)

    def test_invalid_when_never_done(self):
        self.assertFalse(self._user().background_check_valid)

    def test_invalid_when_only_requested_or_submitted(self):
        for status in (User.CHECK_REQUESTED, User.CHECK_SUBMITTED, User.CHECK_REJECTED):
            with self.subTest(status=status):
                user = User(
                    username=status,
                    background_check_status=status,
                    background_check_expires_at=timezone.now() + timedelta(days=1),
                )
                self.assertFalse(user.background_check_valid)

    def test_invalid_when_validated_but_expired(self):
        user = self._user(
            background_check_status=User.CHECK_VALIDATED,
            background_check_expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(user.background_check_valid)
        self.assertTrue(user.background_check_can_upload)

    def test_valid_when_validated_and_not_expired(self):
        user = self._user(
            background_check_status=User.CHECK_VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertTrue(user.background_check_valid)
        self.assertFalse(user.background_check_can_upload)


class LapsedCheckNeverBlocksLoginTests(TestCase):
    """A lapsed background check removes dojo-team access (dojos.access),
    never the login itself (DATA_MODEL.md §10, decision A)."""

    def test_champion_with_expired_check_can_log_in_but_not_open_the_dashboard(self):
        owner = make_champion(username="owner1", email="owner1@example.com")
        owner.set_password(PASSWORD)
        owner.background_check_expires_at = timezone.now() - timedelta(days=1)
        owner.save()
        dojo = make_dojo("Ghent", champion=owner)

        response = self.client.post(reverse("login"), login_data("owner1@example.com", PASSWORD))

        self.assertEqual(int(self.client.session["_auth_user_id"]), owner.id)
        self.assertRedirects(response, reverse("account_home"))
        dashboard = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))
        self.assertEqual(dashboard.status_code, 404)
        account = self.client.get(reverse("account_home"))
        self.assertContains(account, reverse("renew_background_check"))


class VolunteeringCardTests(TestCase):
    """The account page's Volunteering card: applications, check status and
    the next step the account can take."""

    def test_plain_parent_is_offered_both_applications(self):
        parent = User.objects.create(username="parent")
        self.client.force_login(parent)
        response = self.client.get(reverse("account_home"))
        self.assertContains(response, reverse("register_dojo"))
        self.assertContains(response, reverse("register_helper"))

    def test_approved_champion_is_offered_create_a_dojo(self):
        champion = make_champion(username="c1")
        self.client.force_login(champion)
        response = self.client.get(reverse("account_home"))
        self.assertContains(response, reverse("dojo_create"))
        self.assertNotContains(response, f'href="{reverse("register_dojo")}"')

    def test_requested_check_links_to_the_upload_page(self):
        applicant = User.objects.create(username="a1", background_check_status=User.CHECK_REQUESTED)
        Application.objects.create(account=applicant, kind=Application.MENTOR)
        self.client.force_login(applicant)
        response = self.client.get(reverse("account_home"))
        self.assertContains(response, reverse("renew_background_check"))
        self.assertNotContains(response, f'href="{reverse("register_helper")}"')


class NinjaBeltDisplayTests(TestCase):
    def test_ninja_page_shows_current_belt_and_history(self):
        from events.awards import award_belt
        from events.models import Belt

        white = Belt.objects.create(level=1, name="White belt")
        yellow = Belt.objects.create(level=2, name="Yellow belt")
        champion = make_champion(username="champ", first_name="Jan")
        dojo = make_dojo("Ghent", champion=champion)
        guardian = User.objects.create(username="g1", email="g1@example.com")
        child = make_ninja(guardian, "Kid")
        event = Event.objects.create(
            name="Session",
            dojo=dojo,
            start_time="2020-01-01T10:00:00Z",
            end_time="2020-01-01T12:00:00Z",
            places=5,
        )
        Registration.objects.create(event=event, ninja=child, waiting_list=False, position=1)
        award_belt(child, white, dojo.champion_membership)
        award_belt(child, yellow, dojo.champion_membership, note="Built a game")

        self.client.force_login(guardian)
        response = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": child.id}))

        self.assertEqual(response.context["current_belt"], yellow)
        self.assertEqual([a.belt for a in response.context["belt_history"]], [yellow, white])
        self.assertContains(response, "as champion of Ghent")
        self.assertContains(response, "Built a game")

    def test_no_belt_section_without_belts(self):
        guardian = User.objects.create(username="g1", email="g1@example.com")
        child = make_ninja(guardian, "Kid")
        self.client.force_login(guardian)
        response = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": child.id}))
        self.assertIsNone(response.context["current_belt"])
        self.assertNotContains(response, 'id="belt-heading"')

    def test_account_page_shows_each_childs_current_belt(self):
        from events.awards import award_belt
        from events.models import Belt

        white = Belt.objects.create(level=1, name="White belt")
        yellow = Belt.objects.create(level=2, name="Yellow belt")
        dojo = make_dojo("Ghent", champion=make_champion(username="champ"))
        guardian = User.objects.create(username="g1", email="g1@example.com")
        belted = make_ninja(guardian, "Belted")
        make_ninja(guardian, "Unbelted")
        event = Event.objects.create(
            name="Session",
            dojo=dojo,
            start_time="2020-01-01T10:00:00Z",
            end_time="2020-01-01T12:00:00Z",
            places=5,
        )
        Registration.objects.create(event=event, ninja=belted, waiting_list=False, position=1)
        award_belt(belted, white, dojo.champion_membership)
        award_belt(belted, yellow, dojo.champion_membership)

        self.client.force_login(guardian)
        response = self.client.get(reverse("account_home"))

        self.assertContains(response, "Yellow belt")
        self.assertNotContains(response, "White belt")


class OrganisationRoleTests(TestCase):
    """OrganisationRole → a permission group (accounts.organisation): the board
    is read-only (plus the team listing), admins edit the catalogue. Staff
    status only while the Django admin was asked for (accounts.admin_access)."""

    def setUp(self):
        self.user = User.objects.create(username="board1", email="b@example.com")

    def _grant(self, role):
        from .models import OrganisationRole

        return OrganisationRole.objects.create(account=self.user, role=role)

    def _fresh(self):
        return User.objects.get(pk=self.user.pk)  # has_perm caches per instance

    def test_board_role_is_read_only(self):
        from .models import OrganisationRole

        self._grant(OrganisationRole.BOARD)
        user = self._fresh()

        self.assertFalse(user.is_staff)  # only while the Django admin was asked for
        self.assertTrue(user.has_perm("dojos.view_dojo"))
        self.assertTrue(user.has_perm("events.view_ninjabelt"))
        self.assertTrue(user.has_perm("content.change_organisationteammember"))
        self.assertFalse(user.has_perm("dojos.change_dojo"))
        self.assertFalse(user.has_perm("events.add_ninjabelt"))
        self.assertFalse(user.has_perm("accounts.view_ninja"))
        self.assertFalse(user.has_perm("applications.can_review_background_checks"))
        self.assertFalse(user.has_perm("campaigns.view_campaign"))
        self.assertFalse(user.has_perm("mailing.view_emailmessage"))

    def test_admin_role_edits_the_catalogue(self):
        from .models import OrganisationRole

        self._grant(OrganisationRole.ADMIN)
        user = self._fresh()
        self.assertTrue(user.has_perm("dojos.change_dojo"))
        self.assertTrue(user.has_perm("events.add_belt"))
        self.assertTrue(user.has_perm("pathways.change_pathway"))
        self.assertFalse(user.has_perm("events.add_ninjabelt"))

    def test_migrate_refreshes_the_role_groups(self):
        """A permission added to ADMIN_PERMISSIONS reaches existing admins at
        the next migrate (i.e. deploy), not only when a role changes."""
        from django.contrib.auth.models import Group, Permission
        from django.core.management import call_command

        from .models import OrganisationRole
        from .organisation import GROUP_NAMES

        self._grant(OrganisationRole.ADMIN)
        group = Group.objects.get(name=GROUP_NAMES[OrganisationRole.ADMIN])
        group.permissions.remove(Permission.objects.get(codename="view_bouncerecord"))
        self.assertFalse(self._fresh().has_perm("mailing.view_bouncerecord"))

        call_command("migrate", verbosity=0)

        self.assertTrue(self._fresh().has_perm("mailing.view_bouncerecord"))

    def test_only_the_admin_role_runs_campaigns(self):
        from .models import OrganisationRole

        self._grant(OrganisationRole.ADMIN)
        user = self._fresh()
        self.assertTrue(user.has_perm("campaigns.add_campaign"))
        self.assertTrue(user.has_perm("campaigns.change_segmentrule"))
        self.assertTrue(user.has_perm("mailing.change_emailtemplate"))
        self.assertTrue(user.has_perm("mailing.view_emailmessage"))
        self.assertFalse(user.has_perm("mailing.change_emailmessage"))
        self.assertTrue(user.has_perm("mailing.view_consentevent"))
        self.assertTrue(user.has_perm("mailing.add_emailsuppression"))
        self.assertTrue(user.has_perm("mailing.view_bouncerecord"))

    def test_revoking_the_last_role_drops_staff_and_group(self):
        from .models import OrganisationRole

        role = self._grant(OrganisationRole.BOARD)
        role.delete()
        user = self._fresh()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.groups.exists())

    def test_revoking_the_last_role_ends_access_to_the_django_admin(self):
        from accounts.testing import with_admin_access

        from .models import AdminAccessGrant, OrganisationRole

        role = self._grant(OrganisationRole.BOARD)
        self.assertTrue(with_admin_access(self._fresh()).is_staff)
        role.delete()
        self.assertFalse(self._fresh().is_staff)
        self.assertEqual(AdminAccessGrant.objects.get().end_reason, AdminAccessGrant.ROLE_REMOVED)

    def test_ninja_accounts_cannot_hold_a_role(self):
        from django.core.exceptions import ValidationError

        from .models import OrganisationRole

        ninja = User.objects.create(username="n1", account_type=User.NINJA)
        with self.assertRaises(ValidationError):
            OrganisationRole(account=ninja, role=OrganisationRole.BOARD).full_clean()

    def test_menu_links_role_holders_to_the_management_area(self):
        """Every role, the board too, gets the one Manage link; the Django
        admin is asked for there (DATA_MODEL.md §23), never linked directly."""
        from .models import OrganisationRole

        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("account_home")), f'href="{reverse("manage_home")}"')
        self._grant(OrganisationRole.BOARD)
        response = self.client.get(reverse("account_home"))
        self.assertContains(response, f'href="{reverse("manage_home")}"')
        self.assertNotContains(response, f'href="{reverse("admin:index")}"')

    def test_board_sees_applications_but_cannot_run_the_review_actions(self):
        from accounts.testing import with_admin_access

        from .models import OrganisationRole

        self._grant(OrganisationRole.BOARD)
        self.client.force_login(with_admin_access(self._fresh()))
        response = self.client.get(reverse("admin:applications_application_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "approve_applications")
        self.assertEqual(self.client.get(reverse("admin:events_ninjabelt_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:accounts_ninja_changelist")).status_code, 403)


class NinjaAgeRuleTests(TestCase):
    """A ninja is 7–17 (DATA_MODEL.md nomenclature): enforced whenever a date
    of birth is entered or changed, never retroactively."""

    def setUp(self):
        self.guardian = User.objects.create(username="g1", email="g1@example.com")
        self.client.force_login(self.guardian)

    def test_model_clean_checks_new_and_changed_dates_only(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            Ninja(name="Toddler", date_of_birth=timezone.localdate() - timedelta(days=3 * 365)).full_clean()
        Ninja(name="Kid", date_of_birth=timezone.localdate() - timedelta(days=10 * 365)).full_clean()

        grown_up = Ninja.objects.create(name="Now 19", date_of_birth=timezone.localdate() - timedelta(days=19 * 365))
        grown_up.name = "Renamed"
        grown_up.full_clean()  # unchanged date: still editable

    def test_add_child_rejects_an_out_of_range_age(self):
        response = self.client.post(
            reverse("add_ninja"), {"consent": "on", "family_name": "Peeters", "name": "Baby", "date_of_birth": _dob(3)}
        )
        self.assertContains(response, "Ninjas are 7 to 17 years old")
        self.assertFalse(Ninja.objects.of_guardian(self.guardian).exists())

    def test_family_sign_up_flags_the_child_row(self):
        self.client.logout()
        response = self.client.post(
            reverse("register_guardian"),
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                **CHILD_ROWS,
                "child-0-name": "Old",
                "child-0-family_name": "Peeters",
                "child-0-date_of_birth": _dob(19),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ninjas are 7 to 17 years old")
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_edit_rejects_a_changed_out_of_range_date_but_keeps_an_old_one(self):
        grown_up = make_ninja(self.guardian, "Now 19", date_of_birth=timezone.localdate() - timedelta(days=19 * 365))
        url = reverse("edit_ninja", kwargs={"ninja_id": grown_up.id})

        response = self.client.post(url, {"name": "Renamed", "date_of_birth": grown_up.date_of_birth.isoformat()})
        self.assertTemplateUsed(response, "accounts/partials/_child_header_display.html")

        original = grown_up.date_of_birth
        response = self.client.post(url, {"name": "Renamed", "date_of_birth": _dob(4)})
        self.assertTemplateUsed(response, "accounts/partials/_child_header_edit.html")
        self.assertContains(response, "Ninjas are 7 to 17 years old")
        grown_up.refresh_from_db()
        self.assertEqual(grown_up.date_of_birth, original)


class NinjaLoginTests(TestCase):
    """A guardian gives a child their own login, mails the password link
    again and removes it (accounts.child_accounts, DATA_MODEL.md §17)."""

    def setUp(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("load_mail_templates", stdout=StringIO())
        self.guardian = User.objects.create(
            username="ellen",
            email="ellen@example.com",
            first_name="Ellen",
            preferred_language="nl-be",
        )
        self.child = make_ninja(self.guardian, "Emma", date_of_birth=_dob(12))
        self.other_guardian = User.objects.create(username="other", email="other@example.com")
        self.client.force_login(self.guardian)

    def _url(self, name):
        return reverse(name, kwargs={"ninja_id": self.child.id})

    def _create(self, email="emma@example.com", **headers):
        return self.client.post(self._url("ninja_login_create"), {"email": email}, **headers)

    def test_create_makes_a_ninja_login_and_mails_the_child(self):
        from urllib.parse import urlsplit

        from mailing.models import EmailMessage

        response = self._create(HTTP_HX_REQUEST="true")

        self.assertTemplateUsed(response, "accounts/partials/_ninja_login_card.html")
        self.child.refresh_from_db()
        account = self.child.account
        self.assertEqual(
            (account.account_type, account.email, account.first_name), (User.NINJA, "emma@example.com", "Emma")
        )
        self.assertEqual(account.preferred_language, "nl-be")
        self.assertFalse(account.has_usable_password())
        queued = EmailMessage.objects.get(template_key="ninja_account_created")
        self.assertEqual((queued.user, queued.recipient, queued.status), (account, "emma@example.com", "pending"))

        # The link in the mail sets a password the child can log in with.
        link = next(line.strip() for line in queued.body.splitlines() if "/password-reset/confirm/" in line)
        self.client.logout()
        form = self.client.get(urlsplit(link).path, follow=True)
        self.client.post(form.redirect_chain[-1][0], {"new_password1": PASSWORD, "new_password2": PASSWORD})
        response = self.client.post(reverse("login"), login_data("emma@example.com", PASSWORD))
        self.assertRedirects(response, reverse("ninja_detail", kwargs={"ninja_id": self.child.id}))

    def test_email_is_required_and_unique(self):
        def email_errors(email):
            return self._create(email=email, HTTP_HX_REQUEST="true").context["login_form"].errors["email"]

        self.assertIn("email address is needed", email_errors("")[0])
        self.assertEqual(email_errors("ELLEN@example.com"), ["An account already exists with this email."])
        self.child.refresh_from_db()
        self.assertIsNone(self.child.account)

    def test_only_the_childs_guardians_manage_the_login(self):
        self.client.force_login(self.other_guardian)
        self.assertEqual(self._create().status_code, 404)
        self.assertEqual(self.client.post(self._url("ninja_login_remove")).status_code, 404)
        self.child.refresh_from_db()
        self.assertIsNone(self.child.account)

    def test_the_child_cannot_manage_its_own_login(self):
        self._create()
        self.child.refresh_from_db()
        self.client.force_login(self.child.account)
        self.assertEqual(self.client.post(self._url("ninja_login_remove")).status_code, 404)
        self.assertTrue(User.objects.filter(pk=self.child.account_id).exists())

    def test_card_only_shown_to_guardians(self):
        page = self.client.get(self._url("ninja_detail"))
        self.assertTemplateUsed(page, "accounts/partials/_ninja_login_card.html")
        self._create()
        self.child.refresh_from_db()
        self.client.force_login(self.child.account)
        page = self.client.get(self._url("ninja_detail"))
        self.assertTemplateNotUsed(page, "accounts/partials/_ninja_login_card.html")

    def test_resend_queues_another_mail(self):
        from mailing.models import EmailMessage

        self._create()
        self.client.post(self._url("ninja_login_resend"))
        self.assertEqual(EmailMessage.objects.filter(template_key="ninja_account_created").count(), 2)

    def test_remove_deletes_a_login_that_was_never_on_a_team(self):
        self._create()
        self.child.refresh_from_db()
        account_id = self.child.account_id

        response = self.client.post(self._url("ninja_login_remove"))

        self.assertRedirects(response, self._url("ninja_detail"))
        self.assertFalse(User.objects.filter(pk=account_id).exists())
        self.child.refresh_from_db()
        self.assertIsNone(self.child.account)
        self.assertTrue(Ninja.objects.filter(pk=self.child.pk).exists())

    def test_remove_disables_a_youth_mentor_and_ends_their_team_places(self):
        self._create()
        self.child.refresh_from_db()
        account = self.child.account
        dojo = make_dojo("Ghent", champion=make_champion(username="champ"))
        membership = add_member(dojo, account, role=DojoMembership.YOUTH_MENTOR)

        self.client.post(self._url("ninja_login_remove"))

        account.refresh_from_db()
        membership.refresh_from_db()
        self.assertFalse(account.is_active)
        self.assertEqual(membership.status, DojoMembership.DORMANT)
        self.child.refresh_from_db()
        self.assertEqual(self.child.account, account)

        # Switching it back on reuses the same account with a fresh password.
        self._create(email="emma.new@example.com")
        account.refresh_from_db()
        self.assertTrue(account.is_active)
        self.assertEqual(account.email, "emma.new@example.com")
        self.assertFalse(account.has_usable_password())
        self.assertEqual(User.objects.filter(account_type=User.NINJA).count(), 1)

    def test_disabled_login_cannot_log_in(self):
        self._create()
        self.child.refresh_from_db()
        account = self.child.account
        account.set_password(PASSWORD)
        account.save()
        add_member(
            make_dojo("Ghent", champion=make_champion(username="champ")), account, role=DojoMembership.YOUTH_MENTOR
        )
        self.client.post(self._url("ninja_login_remove"))

        self.client.logout()
        response = self.client.post(reverse("login"), login_data("emma@example.com", PASSWORD))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())

    def test_guardian_keeps_editing_a_child_with_a_login(self):
        self._create()
        response = self.client.post(
            self._url("edit_ninja"), {"name": "Emma P.", "date_of_birth": self.child.date_of_birth}
        )
        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "Emma P.")

    def test_child_sees_and_cancels_its_own_upcoming_session(self):
        self._create()
        self.child.refresh_from_db()
        event = Event.objects.create(
            dojo=make_dojo("Ghent"),
            name="Scratch",
            status=Event.OPEN,
            places=5,
            start_time=timezone.now() + timedelta(days=3),
            end_time=timezone.now() + timedelta(days=3, hours=2),
        )
        registration = Registration.objects.create(event=event, ninja=self.child, position=1, waiting_list=False)
        self.client.force_login(self.child.account)

        page = self.client.get(self._url("ninja_detail"))
        self.assertEqual(list(page.context["upcoming"]), [registration])
        self.client.post(reverse("cancel_registration", kwargs={"registration_id": registration.id}))
        self.assertFalse(Registration.objects.filter(pk=registration.pk).exists())


class HomeDojoTests(TestCase):
    """Hybrid home dojo (accounts.home_dojo): set at the first sign-up,
    changeable by the guardian, never moved automatically."""

    def setUp(self):
        self.guardian = User.objects.create(username="g1", email="g1@example.com")
        self.child = make_ninja(self.guardian, "Kid", date_of_birth=_dob(10))
        self.ghent = make_dojo("Ghent")
        self.aalst = make_dojo("Aalst")
        self.client.force_login(self.guardian)

    def _signup(self, dojo):
        now = timezone.now()
        event = Event.objects.create(
            name="S",
            dojo=dojo,
            status=Event.OPEN,
            places=5,
            start_time=now + timedelta(days=3),
            end_time=now + timedelta(days=3, hours=2),
        )
        self.client.post(reverse("event_signup", kwargs={"event_id": event.id}), {"child": [str(self.child.id)]})
        self.child.refresh_from_db()

    def test_first_signup_sets_home_dojo_and_later_ones_dont_move_it(self):
        self._signup(self.ghent)
        self.assertEqual((self.child.home_dojo, self.child.member_since), (self.ghent, timezone.localdate()))
        self._signup(self.aalst)
        self.assertEqual(self.child.home_dojo, self.ghent)

    def test_organisation_dojo_never_becomes_home_dojo(self):
        self._signup(make_dojo("Coolest Projects", kind=Dojo.ORGANISATION))
        self.assertIsNone(self.child.home_dojo)

    def _edit(self, home_dojo):
        return self.client.post(
            reverse("edit_ninja", kwargs={"ninja_id": self.child.id}),
            {
                "name": "Kid",
                "date_of_birth": self.child.date_of_birth,
                "home_dojo": home_dojo,
            },
        )

    def test_guardian_changes_or_clears_it(self):
        self.child.home_dojo, self.child.member_since = self.ghent, timezone.localdate() - timedelta(days=400)
        self.child.save()
        self._edit(self.aalst.id)
        self.child.refresh_from_db()
        self.assertEqual((self.child.home_dojo, self.child.member_since), (self.aalst, timezone.localdate()))

        self._edit("")
        self.child.refresh_from_db()
        self.assertEqual((self.child.home_dojo, self.child.member_since), (None, None))

    def test_same_dojo_keeps_member_since_and_hidden_dojo_is_refused(self):
        since = timezone.localdate() - timedelta(days=400)
        self.child.home_dojo, self.child.member_since = self.ghent, since
        self.child.save()
        self._edit(self.ghent.id)
        self._edit(make_dojo("Draft", status=Dojo.DRAFT).id)
        self.child.refresh_from_db()
        self.assertEqual((self.child.home_dojo, self.child.member_since), (self.ghent, since))

    def test_edit_form_offers_public_dojos(self):
        response = self.client.get(reverse("edit_ninja", kwargs={"ninja_id": self.child.id}))
        self.assertEqual(set(response.context["form"].fields["home_dojo"].queryset), {self.ghent, self.aalst})

    def test_backfill_picks_the_most_attended_dojo(self):
        from io import StringIO

        from django.core.management import call_command

        past = timezone.now() - timedelta(days=30)
        for n, dojo in enumerate([self.aalst, self.ghent, self.ghent]):
            event = Event.objects.create(
                name=f"S{n}",
                dojo=dojo,
                places=5,
                start_time=past + timedelta(days=n),
                end_time=past + timedelta(days=n, hours=2),
            )
            Registration.objects.create(event=event, ninja=self.child, position=1, waiting_list=False, attended=True)

        call_command("assign_home_dojos", stdout=StringIO())
        self.child.refresh_from_db()
        self.assertEqual(self.child.home_dojo, self.ghent)
        self.assertEqual(self.child.member_since, timezone.localdate(past + timedelta(days=1)))

    def test_youth_mentor_role_shows_on_the_childs_page(self):
        login = User.objects.create(username="kid", account_type=User.NINJA)
        self.child.account = login
        self.child.save()
        add_member(self.ghent, login, role=DojoMembership.YOUTH_MENTOR)
        response = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": self.child.id}))
        self.assertContains(response, "Youth mentor")


class SeedCredentialsTests(TestCase):
    """seed_credentials.csv: merged by username (a rerun never drops logins)
    and described from the data, so a tester knows what each login can do."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = patch("accounts.seed_credentials.CREDENTIALS_FILE", Path(self.dir.name) / "seed_credentials.csv")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_rerun_merges_instead_of_replacing(self):
        from .seed_credentials import read_credentials, write_credentials

        User.objects.create(username="m1", email="m1@coderdojo-demo.example")
        User.objects.create(username="m2", email="m2@coderdojo-demo.example")
        write_credentials("mentor", [("m1", "m1@coderdojo-demo.example", "pw1")])
        write_credentials("mentor", [("m2", "m2@coderdojo-demo.example", "pw2")])
        self.assertEqual({r["username"] for r in read_credentials()}, {"m1", "m2"})

    def test_descriptions_say_what_the_login_can_do(self):
        from .seed_credentials import describe_account

        parent = User.objects.create(username="p", email="p@coderdojo-demo.example")
        kid_login = User.objects.create(username="k", account_type=User.NINJA)
        make_ninja(parent, "Emma", date_of_birth=_dob(12), account=kid_login)
        make_ninja(parent, "Lucas", date_of_birth=_dob(9))
        dojo = make_dojo("Ghent", champion=make_champion(username="champ"), languages=["nl-be", "en-us"])
        add_member(dojo, kid_login, role=DojoMembership.YOUTH_MENTOR)

        # Emma's guardian consented (accounts.consent); Lucas was linked without.
        Guardianship.objects.filter(guardian=parent, ninja__name="Emma").update(consent_given_at=timezone.now())
        self.assertIn("Parent of 2 children: Emma (12) [own login], Lucas (9) [no consent]", describe_account(parent))
        kid = describe_account(kid_login)
        self.assertIn("Child login of Emma (12)", kid)
        self.assertIn("Youth mentor at Ghent (NL/EN)", kid)
        self.assertIn("Champion of 1 dojo: Ghent (NL/EN)", describe_account(User.objects.get(username="champ")))

    @override_settings(DEBUG=True)
    def test_command_gives_missing_seeded_logins_a_password(self):
        from io import StringIO

        from django.core.management import call_command

        from .seed_credentials import read_credentials

        seeded = User.objects.create(username="lost", email="lost@coderdojo-demo.example")
        User.objects.create(username="real", email="someone@gmail.com")
        call_command("describe_seed_accounts", stdout=StringIO())
        rows = {r["username"]: r for r in read_credentials()}
        self.assertEqual(set(rows), {"lost"})
        seeded.refresh_from_db()
        self.assertTrue(seeded.check_password(rows["lost"]["password"]))
        self.assertIn("Plain adult account", rows["lost"]["description"])


class ChildHealthNotesTests(TestCase):
    """The family keeps a child's allergies or notes up to date on the
    account pages (add a child, edit a child); only the dojo's champion sees
    them (dojos.access.VIEW_HEALTH_NOTES)."""

    def setUp(self):
        from .models import Guardianship

        self.parent = User.objects.create(username="parent", email="parent@example.com")
        self.child = Ninja.objects.create(name="Emma", allergies_notes="Peanut allergy")
        Guardianship.objects.create(guardian=self.parent, ninja=self.child)
        self.client.force_login(self.parent)
        self.edit_url = reverse("edit_ninja", kwargs={"ninja_id": self.child.id})

    def test_add_a_child_with_notes(self):
        self.client.post(
            reverse("add_ninja"),
            {"consent": "on", "family_name": "Peeters", "name": "Lou", "allergies_notes": "  Gluten-free  "},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(Ninja.objects.get(name="Lou").allergies_notes, "Gluten-free")

    def test_edit_form_shows_and_saves_the_notes(self):
        response = self.client.get(self.edit_url, HTTP_HX_REQUEST="true")
        self.assertContains(response, 'name="allergies_notes"')
        self.assertContains(response, "Peanut allergy")
        self.assertContains(response, "Only the champion")
        response = self.client.post(
            self.edit_url, {"name": "Emma", "allergies_notes": "Asthma inhaler"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "Asthma inhaler")
        self.child.refresh_from_db()
        self.assertEqual(self.child.allergies_notes, "Asthma inhaler")

    def test_clearing_the_notes(self):
        self.client.post(self.edit_url, {"name": "Emma", "allergies_notes": ""}, HTTP_HX_REQUEST="true")
        self.child.refresh_from_db()
        self.assertEqual(self.child.allergies_notes, "")

    def test_a_form_without_the_field_keeps_them(self):
        self.client.post(self.edit_url, {"name": "Emma"}, HTTP_HX_REQUEST="true")
        self.child.refresh_from_db()
        self.assertEqual(self.child.allergies_notes, "Peanut allergy")

    def test_the_child_page_shows_them_to_the_family(self):
        response = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": self.child.id}))
        self.assertContains(response, "Peanut allergy")

    def test_another_family_cannot_edit_them(self):
        other = User.objects.create(username="other", email="other@example.com")
        self.client.force_login(other)
        response = self.client.post(self.edit_url, {"name": "Emma", "allergies_notes": "x"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 404)
        self.child.refresh_from_db()
        self.assertEqual(self.child.allergies_notes, "Peanut allergy")


# --- Two-step login and the sign-in policy (DATA_MODEL.md §15) -------------

FAKE_REGISTRATION = (
    '{"id": "cGFzc2tleQ", "rawId": "cGFzc2tleQ", "type": "public-key", '
    '"response": {"clientDataJSON": "e30", "attestationObject": "oA"}}'
)
FAKE_ASSERTION = (
    '{"id": "cGFzc2tleQ", "rawId": "cGFzc2tleQ", "type": "public-key", '
    '"response": {"clientDataJSON": "e30", "authenticatorData": "AA", "signature": "AA", "userHandle": null}}'
)


class TwoStepTestMixin:
    """An adult account with a password, and the mail templates loaded."""

    def setUp(self):
        from io import StringIO

        from django.core.management import call_command

        from . import sign_in

        super().setUp()
        # The sign-in policy is cached (accounts.sign_in.policy) and a test's
        # rollback sends no signal: forget any policy a test set.
        self.addCleanup(sign_in.clear_policy_cache)
        call_command("load_mail_templates", stdout=StringIO())
        self.user = User.objects.create(username="ann", email="ann@example.com", first_name="Ann")
        self.user.set_password(PASSWORD)
        self.user.save()

    def queued(self, key):
        from mailing.models import EmailMessage

        return EmailMessage.objects.filter(user=self.user, template_key=key)

    def add_app(self, user=None):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        return TOTPDevice.objects.create(user=user or self.user, name="default")

    def add_passkey(self, user=None, name="default"):
        from two_factor.plugins.webauthn.models import WebauthnDevice

        return WebauthnDevice.objects.create(
            user=user or self.user,
            name=name,
            public_key="pk",
            key_handle="cGFzc2tleQ",
            sign_count=0,
        )


class TwoStepLoginTests(TwoStepTestMixin, TestCase):
    """accounts.views.LoginView: password, then a code, passkey or backup code."""

    def test_without_two_step_login_the_password_is_enough(self):
        response = self.client.post(reverse("login"), login_data("ann@example.com", PASSWORD))
        self.assertRedirects(response, reverse("account_home"))

    def test_with_an_app_the_password_leads_to_the_code_step(self):
        self.add_app()
        response = self.client.post(reverse("login"), login_data("ann@example.com", PASSWORD))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["wizard"]["steps"].current, "token")
        self.assertEqual(response.context["device_kind"], "app")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_wrong_code_is_refused(self):
        from core.testing import token_data

        self.add_app()
        self.client.post(reverse("login"), login_data("ann@example.com", PASSWORD))
        response = self.client.post(reverse("login"), token_data("000000"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_right_code_logs_in_verified(self):
        from django_otp import DEVICE_ID_SESSION_KEY

        from core.testing import token_data, totp_code

        device = self.add_app()
        self.client.post(reverse("login"), login_data("ann", PASSWORD))
        response = self.client.post(reverse("login"), token_data(totp_code(device)))
        self.assertRedirects(response, reverse("account_home"))
        self.assertEqual(self.client.session[DEVICE_ID_SESSION_KEY], device.persistent_id)

    def test_next_survives_both_steps(self):
        from core.testing import token_data, totp_code

        device = self.add_app()
        url = reverse("login") + "?next=/account/security/"
        self.client.post(url, {**login_data("ann", PASSWORD), "next": "/account/security/"})
        response = self.client.post(url, {**token_data(totp_code(device)), "next": "/account/security/"})
        self.assertRedirects(response, "/account/security/")

    def test_a_remembered_browser_skips_the_code_step(self):
        from core.testing import token_data, totp_code

        device = self.add_app()
        self.client.post(reverse("login"), login_data("ann", PASSWORD))
        self.client.post(reverse("login"), {**token_data(totp_code(device)), "token-remember": "on"})
        remembered = {
            key: morsel.value for key, morsel in self.client.cookies.items() if key.startswith("remember-cookie_")
        }
        self.assertTrue(remembered)
        self.client.logout()  # the test client's logout drops every cookie; a browser keeps this one
        self.client.cookies.load(remembered)
        response = self.client.post(reverse("login"), login_data("ann", PASSWORD))
        self.assertRedirects(response, reverse("account_home"))

    def test_a_backup_code_logs_in_once_and_mails(self):
        from core.testing import token_data

        from . import two_step

        self.add_app()
        code = two_step.make_backup_codes(self.user)[0]
        self.client.post(reverse("login"), login_data("ann", PASSWORD))
        self.client.post(reverse("login"), {"login_view-current_step": "token", "wizard_goto_step": "backup"})
        response = self.client.post(reverse("login"), token_data(code, step="backup"))
        self.assertRedirects(response, reverse("account_home"))
        self.assertEqual(two_step.backup_codes_left(self.user), two_step.BACKUP_CODE_COUNT - 1)
        self.assertIn("9", self.queued("backup_code_used").get().body)

    def test_a_passkey_logs_in(self):
        from core.testing import token_data

        self.add_passkey()
        response = self.client.post(reverse("login"), login_data("ann", PASSWORD))
        self.assertEqual(response.context["device_kind"], "passkey")
        self.assertIn("challenge", response.context["passkey_options"])
        with patch("two_factor.plugins.webauthn.forms.verify_authentication_response", return_value=1):
            response = self.client.post(reverse("login"), token_data(FAKE_ASSERTION))
        self.assertRedirects(response, reverse("account_home"))

    def test_a_passkey_that_doesnt_check_out_is_refused(self):
        from webauthn.helpers.exceptions import InvalidAuthenticationResponse

        from core.testing import token_data

        self.add_passkey()
        self.client.post(reverse("login"), login_data("ann", PASSWORD))
        with patch(
            "two_factor.plugins.webauthn.forms.verify_authentication_response",
            side_effect=InvalidAuthenticationResponse("bad"),
        ):
            response = self.client.post(reverse("login"), token_data(FAKE_ASSERTION))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_other_method_is_offered(self):
        self.add_app()
        self.add_passkey(name="passkey")
        response = self.client.post(reverse("login"), login_data("ann", PASSWORD))
        self.assertEqual([kind for _id, kind in response.context["other_kinds"]], ["passkey"])

    def test_the_admin_login_sends_to_the_site_login(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))


class SignInSecurityPageTests(TwoStepTestMixin, TestCase):
    """accounts.security_views: the account's own Sign-in security pages."""

    def verified(self):
        from core.testing import login_verified

        return login_verified(self.client, self.user)

    def test_needs_a_login(self):
        response = self.client.get(reverse("account_security"))
        self.assertIn(reverse("login"), response["Location"])

    def test_a_ninja_login_has_it_too_but_not_a_service_account(self):
        """Every person's login has the same options (DATA_MODEL.md §24)."""
        ninja = User.objects.create(username="kid", account_type=User.NINJA)
        self.client.force_login(ninja)
        self.assertEqual(self.client.get(reverse("account_security")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_security_app")).status_code, 200)
        service = User.objects.create(username="svc", account_type=User.SERVICE)
        self.client.force_login(service)
        self.assertEqual(self.client.get(reverse("account_security")).status_code, 404)

    def test_the_account_page_links_to_it(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("account_home")), reverse("account_security"))

    def test_setting_up_an_app_turns_two_step_login_on(self):
        from django_otp import DEVICE_ID_SESSION_KEY
        from django_otp.plugins.otp_totp.models import TOTPDevice
        from django_otp.util import random_hex

        from core.testing import totp_code

        from . import two_step
        from .security_views import APP_KEY_SESSION

        self.client.force_login(self.user)
        response = self.client.get(reverse("account_security_app"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("<svg", response.context["qr_svg"])
        key = self.client.session[APP_KEY_SESSION]
        code = totp_code(TOTPDevice(key=key or random_hex(20)))
        response = self.client.post(reverse("account_security_app"), {"token": code})
        self.assertRedirects(response, reverse("account_security_backup_codes"), fetch_redirect_response=False)
        device = two_step.app_device(self.user)
        self.assertEqual(device.name, "default")
        self.assertEqual(self.client.session[DEVICE_ID_SESSION_KEY], device.persistent_id)
        self.assertEqual(len(self.client.get(reverse("account_security_backup_codes")).context["codes"]), 10)
        self.assertEqual(self.queued("two_step_turned_on").count(), 1)

    def test_a_wrong_first_code_saves_nothing(self):
        from . import two_step

        self.client.force_login(self.user)
        self.client.get(reverse("account_security_app"))
        response = self.client.post(reverse("account_security_app"), {"token": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(two_step.is_on(self.user))

    def test_adding_a_passkey(self):
        from . import two_step

        self.client.force_login(self.user)
        response = self.client.get(reverse("account_security_passkey"))
        self.assertIn("challenge", response.context["passkey_options"])
        with patch("two_factor.plugins.webauthn.method.verify_registration_response", return_value=("pk", "kh", 0)):
            response = self.client.post(reverse("account_security_passkey"), {"token": FAKE_REGISTRATION})
        self.assertRedirects(response, reverse("account_security_backup_codes"))
        self.assertTrue(two_step.has_passkey(self.user))
        self.assertIn("your passkey", self.queued("two_step_turned_on").get().body)

    def test_a_second_method_is_not_the_default_and_mails_as_added(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        self.verified()
        self.client.get(reverse("account_security_passkey"))
        with patch("two_factor.plugins.webauthn.method.verify_registration_response", return_value=("pk", "kh", 0)):
            response = self.client.post(reverse("account_security_passkey"), {"token": FAKE_REGISTRATION})
        self.assertRedirects(response, reverse("account_security"))
        self.assertEqual(TOTPDevice.objects.get(user=self.user).name, "default")
        self.assertEqual(self.queued("two_step_method_added").count(), 1)

    def test_a_passkey_that_doesnt_check_out_is_not_saved(self):
        from webauthn.helpers.exceptions import InvalidRegistrationResponse

        from . import two_step

        self.client.force_login(self.user)
        self.client.get(reverse("account_security_passkey"))
        with patch(
            "two_factor.plugins.webauthn.method.verify_registration_response",
            side_effect=InvalidRegistrationResponse("bad"),
        ):
            response = self.client.post(reverse("account_security_passkey"), {"token": FAKE_REGISTRATION})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["error"])
        self.assertFalse(two_step.is_on(self.user))

    def test_changes_need_a_session_that_passed_two_step_login(self):
        self.add_app()
        self.client.force_login(self.user)  # an older login, before the app
        response = self.client.get(reverse("account_security_backup_codes"))
        self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_removing_needs_the_password(self):
        from . import two_step

        device = self.verified()
        url = reverse("account_security_remove", kwargs={"kind": "app", "device_id": device.pk})
        self.assertEqual(self.client.post(url, {"password": "wrong"}).status_code, 200)
        self.assertTrue(two_step.is_on(self.user))
        self.assertRedirects(self.client.post(url, {"password": PASSWORD}), reverse("account_security"))
        self.assertFalse(two_step.is_on(self.user))

    def test_removing_the_last_method_turns_it_off_and_drops_the_backup_codes(self):
        from django_otp.plugins.otp_static.models import StaticDevice

        from . import two_step

        device = self.verified()
        two_step.make_backup_codes(self.user)
        url = reverse("account_security_remove", kwargs={"kind": "app", "device_id": device.pk})
        self.client.post(url, {"password": PASSWORD})
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())
        self.assertEqual(self.queued("two_step_turned_off").count(), 1)

    def test_removing_the_default_makes_another_method_the_default(self):
        from . import two_step

        device = self.verified()
        passkey = self.add_passkey(name="passkey")
        url = reverse("account_security_remove", kwargs={"kind": "app", "device_id": device.pk})
        self.client.post(url, {"password": PASSWORD})
        passkey.refresh_from_db()
        self.assertEqual(passkey.name, "default")
        self.assertTrue(two_step.is_on(self.user))
        self.assertEqual(self.queued("two_step_method_removed").count(), 1)

    def test_someone_elses_device_is_a_404(self):
        other = User.objects.create(username="bob")
        device = self.add_app(user=other)
        self.verified()
        url = reverse("account_security_remove", kwargs={"kind": "app", "device_id": device.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_turning_it_off(self):
        from . import two_step

        self.verified()
        self.add_passkey(name="passkey")
        response = self.client.post(reverse("account_security_turn_off"), {"password": PASSWORD})
        self.assertRedirects(response, reverse("account_security"))
        self.assertFalse(two_step.is_on(self.user))

    def test_a_role_that_needs_it_blocks_turning_it_off(self):
        from . import two_step
        from .models import SignInRequirement

        SignInRequirement.objects.create(role=SignInRequirement.ADULT, level=SignInRequirement.TWO_STEP)
        self.verified()
        response = self.client.post(reverse("account_security_turn_off"), {"password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["blocked"])
        self.assertTrue(two_step.is_on(self.user))

    def test_new_backup_codes_replace_the_old_ones(self):
        from . import two_step

        self.verified()
        old = two_step.make_backup_codes(self.user)
        self.client.post(reverse("account_security_backup_codes"))
        new = self.client.get(reverse("account_security_backup_codes")).context["codes"]
        self.assertFalse(set(old) & set(new))
        self.assertIsNone(self.client.get(reverse("account_security_backup_codes")).context["codes"])

    def test_forgetting_this_browser_deletes_the_cookie(self):
        self.verified()
        self.client.cookies["remember-cookie_abc"] = "x"
        response = self.client.post(reverse("account_security_forget_browser"))
        self.assertEqual(response.cookies["remember-cookie_abc"].value, "")


class SignInPolicyTests(TwoStepTestMixin, TestCase):
    """accounts.sign_in: the organisation's sign-in policy per role, and
    where it's applied."""

    def require(self, role, level=None, required_from=None):
        from .models import SignInRequirement

        return SignInRequirement.objects.create(
            role=role,
            level=level or SignInRequirement.TWO_STEP,
            required_from=required_from,
        )

    def test_roles_of(self):
        from . import sign_in
        from .models import OrganisationRole, SignInRequirement

        champion = make_champion(username="champ")
        make_dojo("Ghent", champion=champion)
        mentor = make_mentor(username="ment")
        add_member(Dojo.objects.get(name="Ghent"), mentor)
        OrganisationRole.objects.create(account=self.user, role=OrganisationRole.BOARD)
        ninja = User.objects.create(username="kid", account_type=User.NINJA)
        self.assertEqual(sign_in.roles_of(champion) - {SignInRequirement.ADULT}, {SignInRequirement.CHAMPION})
        self.assertEqual(sign_in.roles_of(mentor) - {SignInRequirement.ADULT}, {SignInRequirement.MENTOR})
        self.assertEqual(sign_in.roles_of(self.user), {SignInRequirement.ADULT, SignInRequirement.ORGANISATION_BOARD})
        self.assertEqual(sign_in.roles_of(ninja), set())
        self.assertIn(champion, sign_in.accounts_with_role(SignInRequirement.CHAMPION))
        self.assertIn(self.user, sign_in.accounts_with_role(SignInRequirement.ORGANISATION_BOARD))

    def test_the_strongest_level_applies_and_a_later_one_is_upcoming(self):
        from . import sign_in
        from .models import OrganisationRole, SignInRequirement

        OrganisationRole.objects.create(account=self.user, role=OrganisationRole.ADMIN)
        self.require(SignInRequirement.ADULT)
        later = timezone.localdate() + timedelta(days=10)
        self.require(SignInRequirement.ORGANISATION_ADMIN, SignInRequirement.PASSKEY, required_from=later)
        enforced, upcoming = sign_in.requirements_for(self.user)
        self.assertEqual(enforced.level, SignInRequirement.TWO_STEP)
        self.assertEqual((upcoming.level, upcoming.required_from), (SignInRequirement.PASSKEY, later))
        enforced, upcoming = sign_in.requirements_for(self.user, today=later)
        self.assertEqual((enforced.level, upcoming), (SignInRequirement.PASSKEY, None))

    def test_without_a_policy_nothing_changes(self):
        from . import sign_in

        enforced, upcoming = sign_in.requirements_for(self.user)
        self.assertEqual((enforced.level, upcoming), (sign_in.PASSWORD, None))

    def test_status(self):
        from . import sign_in
        from .sign_in import Requirement

        two_step_rule, passkey_rule = Requirement(sign_in.TWO_STEP), Requirement(sign_in.PASSKEY)
        self.assertEqual(sign_in.status(self.user, False, two_step_rule), sign_in.NEEDS_SETUP)
        self.add_app()
        self.assertEqual(sign_in.status(self.user, False, two_step_rule), sign_in.NEEDS_VERIFY)
        self.assertEqual(sign_in.status(self.user, True, two_step_rule), sign_in.OK)
        self.assertEqual(sign_in.status(self.user, True, passkey_rule), sign_in.NEEDS_SETUP)

    def test_an_account_without_the_device_is_sent_to_set_it_up(self):
        from .models import SignInRequirement

        self.require(SignInRequirement.ADULT)
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse("account_home")), reverse("account_security"))
        self.assertEqual(self.client.get(reverse("account_security")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_security_app")).status_code, 200)

    def test_htmx_gets_a_whole_page_redirect(self):
        from .models import SignInRequirement

        self.require(SignInRequirement.ADULT)
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_home"), headers={"HX-Request": "true"})
        self.assertEqual(response["HX-Redirect"], reverse("account_security"))

    def test_a_session_that_skipped_the_second_step_logs_in_again(self):
        from .models import SignInRequirement

        self.require(SignInRequirement.ADULT)
        self.add_app()
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_home"))
        self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_verified_session_carries_on(self):
        from core.testing import login_verified

        from .models import SignInRequirement

        self.require(SignInRequirement.ADULT)
        login_verified(self.client, self.user)
        self.assertEqual(self.client.get(reverse("account_home")).status_code, 200)

    def test_a_ninja_login_is_never_asked(self):
        from .models import SignInRequirement

        self.require(SignInRequirement.ADULT)
        child = make_ninja(self.user, "Emma")
        login = User.objects.create(username="emma", account_type=User.NINJA)
        child.account = login
        child.save()
        self.client.force_login(login)
        self.assertEqual(self.client.get(reverse("ninja_detail", kwargs={"ninja_id": child.id})).status_code, 200)

    def test_a_future_requirement_is_only_a_notice(self):
        from .models import SignInRequirement

        self.require(SignInRequirement.ADULT, required_from=timezone.localdate() + timedelta(days=7))
        self.client.force_login(self.user)
        response = self.client.get(reverse("account_home"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["sign_in_notice"]())
        self.assertContains(response, reverse("account_security"))

    def test_the_dojo_area_needs_it_for_mentors(self):
        from core.testing import login_verified

        from .models import SignInRequirement

        champion = make_champion(username="champ")
        dojo = make_dojo("Ghent", champion=champion)
        self.require(SignInRequirement.CHAMPION)
        self.client.force_login(champion)
        dashboard = reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id})
        self.assertRedirects(self.client.get(dashboard), reverse("account_security"))
        login_verified(self.client, champion)
        self.assertEqual(self.client.get(dashboard).status_code, 200)

    def test_the_access_helpers_refuse_even_without_the_middleware(self):
        from django.http import Http404
        from django.test import RequestFactory

        from dojos.access import require_dojo_access

        from .models import OrganisationRole, SignInRequirement
        from .organisation import Area, require_area

        champion = make_champion(username="champ")
        dojo = make_dojo("Ghent", champion=champion)
        OrganisationRole.objects.create(account=champion, role=OrganisationRole.ADMIN)
        self.require(SignInRequirement.CHAMPION)
        self.require(SignInRequirement.ORGANISATION_ADMIN)
        request = RequestFactory().get("/")
        request.user = champion
        with self.assertRaises(Http404):
            require_dojo_access(request, dojo.id)
        with self.assertRaises(Http404):
            require_area(request, Area.COMMUNICATION)

    def test_the_django_admin_needs_it_for_superusers(self):
        from django.contrib import admin
        from django.test import RequestFactory

        from core.testing import login_verified

        from .models import SignInRequirement

        root = User.objects.create(username="root", is_staff=True, is_superuser=True)
        self.require(SignInRequirement.SUPERUSER)
        request = RequestFactory().get("/admin/")
        request.user = root
        self.assertFalse(admin.site.has_permission(request))
        login_verified(self.client, root)
        self.assertEqual(self.client.get("/admin/").status_code, 200)


class ManageSignInSecurityTests(TwoStepTestMixin, TestCase):
    """accounts.manage: the organisation dashboard's Sign-in security page."""

    def setUp(self):
        from .models import OrganisationRole

        super().setUp()
        self.admin = User.objects.create(username="orgadmin", email="orgadmin@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)

    def test_only_the_organisation_admin_role(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("manage_security")).status_code, 404)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage_security"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/manage/security.html")

    def test_saving_the_policy(self):
        from .models import SignInRequirement

        self.client.force_login(self.admin)
        data = {f"level_{role}": SignInRequirement.PASSWORD for role, _label in SignInRequirement.ROLE_CHOICES}
        data.update({"level_mentor": SignInRequirement.TWO_STEP, "from_mentor": "2030-01-01"})
        self.assertRedirects(self.client.post(reverse("manage_security"), data), reverse("manage_security"))
        row = SignInRequirement.objects.get()
        self.assertEqual(
            (row.role, row.level, str(row.required_from), row.updated_by),
            (
                SignInRequirement.MENTOR,
                SignInRequirement.TWO_STEP,
                "2030-01-01",
                self.admin,
            ),
        )

    def test_counts_per_role(self):
        from .models import SignInRequirement

        self.add_app()
        User.objects.filter(pk=self.user.pk).update(login_method=User.LOGIN_LINK)
        self.client.force_login(self.admin)
        rows = {row[0]: row[-1] for row in self.client.get(reverse("manage_security")).context["rows"]}
        self.assertEqual(rows[SignInRequirement.ADULT], {"total": 2, "on": 1, "passkey": 0, "link": 1})

    def test_turning_off_someones_two_step_login(self):
        from . import two_step

        self.add_app()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage_security"), {"q": "ann"})
        self.assertEqual([account.pk for account in response.context["accounts"]], [self.user.pk])
        self.client.post(reverse("manage_security_turn_off", kwargs={"user_id": self.user.pk}))
        self.assertFalse(two_step.is_on(self.user))
        self.assertIn("As you asked us", self.queued("two_step_turned_off").get().body)

    def test_not_ones_own(self):
        from . import two_step

        self.add_app(user=self.admin)
        self.client.force_login(self.admin)
        self.client.post(reverse("manage_security_turn_off", kwargs={"user_id": self.admin.pk}))
        self.assertTrue(two_step.is_on(self.admin))


class SeedTwoStepTests(TestCase):
    """seed_two_step, totp_code and the credentials file's totp_secret column."""

    def test_seeds_one_account_per_kind_once(self):
        from io import StringIO

        from django.core.management import call_command

        from . import two_step
        from .models import OrganisationRole
        from .seed_credentials import totp_secret

        admin = User.objects.create(username="org-a", email="a@coderdojobelgium.example")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        parent = User.objects.create(username="parent-a", email="p@coderdojo-demo.example")
        make_ninja(parent, "Emma")
        outsider = User.objects.create(username="real", email="real@example.com")
        call_command("seed_two_step", stdout=StringIO())
        self.assertTrue(two_step.is_on(admin) and two_step.is_on(parent))
        self.assertFalse(two_step.is_on(outsider))
        self.assertEqual(two_step.backup_codes_left(admin), two_step.BACKUP_CODE_COUNT)
        key = totp_secret(admin)
        self.assertEqual(len(key), 32)
        call_command("seed_two_step", stdout=StringIO())
        self.assertEqual(totp_secret(admin), key)
        self.assertEqual(totp_secret(outsider), "")

    @override_settings(DEBUG=True)
    def test_totp_code_prints_the_current_code(self):
        from io import StringIO

        from django.core.management import call_command
        from django_otp.plugins.otp_totp.models import TOTPDevice

        from core.testing import totp_code

        user = User.objects.create(username="ann")
        device = TOTPDevice.objects.create(user=user, name="default")
        out = StringIO()
        call_command("totp_code", "ann", stdout=out)
        self.assertEqual(out.getvalue().strip(), totp_code(device))


class SeedOtpVaultTests(TestCase):
    """seed_otp_vault: the testers' authenticator (2FAuth) follows the data's apps."""

    def run_command(self, existing):
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command

        session = mock.MagicMock()
        session.get.return_value.json.return_value = existing
        with mock.patch("accounts.management.commands.seed_otp_vault.requests.Session", return_value=session):
            call_command("seed_otp_vault", stdout=StringIO())
        return session

    @override_settings(OTP_VAULT_URL="")
    def test_does_nothing_without_a_vault(self):
        session = self.run_command([])
        session.get.assert_not_called()

    @override_settings(OTP_VAULT_URL="http://otp:8000")
    def test_adds_new_keys_replaces_changed_ones_and_keeps_the_rest(self):
        from base64 import b32encode

        from django_otp.plugins.otp_totp.models import TOTPDevice

        from .management.commands.seed_otp_vault import SERVICE

        def entry(pk, device, secret=None):
            key = secret or b32encode(device.bin_key).decode("ascii")
            account = device.user.username
            return {"id": pk, "service": SERVICE, "account": account, "secret": key, "digits": 6, "period": 30}

        same = TOTPDevice.objects.create(user=User.objects.create(username="same"), name="default")
        changed = TOTPDevice.objects.create(user=User.objects.create(username="changed"), name="default")
        new = TOTPDevice.objects.create(user=User.objects.create(username="new"), name="default")
        TOTPDevice.objects.create(user=User.objects.create(username="unconfirmed"), name="default", confirmed=False)
        gone = {"id": 4, "service": SERVICE, "account": "gone", "secret": "AAAA", "digits": 6, "period": 30}
        by_hand = {"id": 5, "service": "Something else", "account": "x", "secret": "BBBB", "digits": 6, "period": 30}

        session = self.run_command([entry(1, same), entry(2, changed, secret="OLDKEY"), gone, by_hand])

        deleted = sorted(call.args[0] for call in session.delete.call_args_list)
        self.assertEqual(deleted, ["http://otp:8000/api/v1/twofaccounts/2", "http://otp:8000/api/v1/twofaccounts/4"])
        posted = sorted(call.kwargs["json"]["account"] for call in session.post.call_args_list)
        self.assertEqual(posted, ["changed", "new"])
        new_entry = next(c.kwargs["json"] for c in session.post.call_args_list if c.kwargs["json"]["account"] == "new")
        self.assertEqual(new_entry["secret"], b32encode(new.bin_key).decode("ascii"))
        self.assertEqual(session.headers.update.call_args.args[0]["Remote-User"], "testers")


class ChildFamilyNameTests(TestCase):
    """A child's first and family name (Ninja.name + family_name): asked for
    when a child is added, shown in full to the dojo team."""

    def setUp(self):
        self.guardian = User.objects.create(username="g", email="g@example.com", first_name="Ann", last_name="Peeters")
        self.client.force_login(self.guardian)

    def test_full_name(self):
        self.assertEqual(Ninja(name="Emma", family_name="Peeters").full_name, "Emma Peeters")
        self.assertEqual(str(Ninja(name="Emma", family_name="Peeters")), "Emma Peeters")
        self.assertEqual(Ninja(name="Emma").full_name, "Emma")

    def test_sign_up_asks_for_each_childs_family_name(self):
        self.client.logout()
        data = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "",
            "password": "a-brand-new-password-99",
            "consent": "on",
            **CHILD_ROWS,
            "child-0-name": "Sam",
            "child-0-family_name": "",
            "child-0-date_of_birth": _dob(10),
        }
        response = self.client.post(reverse("register_guardian"), data)
        self.assertContains(response, "Family name is required.")
        self.assertFalse(Ninja.objects.exists())
        data["child-0-family_name"] = "Doe"
        self.client.post(reverse("register_guardian"), data)
        self.assertEqual(Ninja.objects.get().full_name, "Sam Doe")

    def test_add_a_child_prefills_and_needs_the_family_name(self):
        self.assertContains(self.client.get(reverse("account_home")), 'name="family_name" value="Peeters"')
        response = self.client.post(reverse("add_ninja"), {"consent": "on", "name": "Lou", "family_name": ""})
        self.assertContains(response, "Family name is required.")
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "Lou", "family_name": "Maes"})
        self.assertEqual(Ninja.objects.of_guardian(self.guardian).get().full_name, "Lou Maes")

    def test_editing_saves_the_family_name(self):
        child = make_ninja(self.guardian, "Lou")
        self.client.post(
            reverse("edit_ninja", kwargs={"ninja_id": child.id}), {"name": "Lou", "family_name": "Peeters"}
        )
        child.refresh_from_db()
        self.assertEqual(child.full_name, "Lou Peeters")

    def test_the_dojo_team_sees_the_full_name(self):
        champion = make_champion(username="champ")
        dojo = make_dojo("Ghent", champion=champion)
        event = Event.objects.create(
            name="Session",
            dojo=dojo,
            status=Event.OPEN,
            places=10,
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=2),
        )
        child = Ninja.objects.create(name="Emma", family_name="Peeters")
        Registration.objects.create(event=event, ninja=child, waiting_list=False, position=1)
        self.client.force_login(champion)
        url = reverse("dojo_event_attendance", kwargs={"dojo_id": dojo.id, "event_id": event.id})
        self.assertContains(self.client.get(url), "Emma Peeters")

    def test_the_migration_splits_only_a_guardians_family_name(self):
        from importlib import import_module

        from django.apps import apps

        split = import_module("accounts.migrations.0011_ninja_family_name").split_family_names
        known = make_ninja(self.guardian, "Emma Peeters")
        unknown = make_ninja(self.guardian, "Lou Van Damme")
        split(apps, None)
        known.refresh_from_db()
        unknown.refresh_from_db()
        self.assertEqual((known.name, known.family_name), ("Emma", "Peeters"))
        self.assertEqual((unknown.name, unknown.family_name), ("Lou Van Damme", ""))


class AdminAccessTests(TestCase):
    """Time-boxed access to the Django admin (accounts.admin_access,
    DATA_MODEL.md §23): asked for with a reason and the password, 12 hours,
    then closed; recorded in the audit log, and the other organisation
    admins get a notification. Superusers are never time-boxed."""

    def setUp(self):
        from .models import OrganisationRole

        self.admin = User.objects.create(username="admin1", email="a1@example.com", first_name="Ann")
        self.admin.set_password(PASSWORD)
        self.admin.save()
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.other_admin = User.objects.create(username="admin2", email="a2@example.com")
        OrganisationRole.objects.create(account=self.other_admin, role=OrganisationRole.ADMIN)
        self.reviewer = User.objects.create(username="rev", email="rev@example.com")
        OrganisationRole.objects.create(account=self.reviewer, role=OrganisationRole.REVIEWER)

    def _ask(self, reason="Fix a registration", password=PASSWORD):
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("manage_admin_access"), {"reason": reason, "password": password})

    def _fresh(self, user):
        return User.objects.get(pk=user.pk)

    def test_a_role_alone_never_opens_the_django_admin(self):
        self.client.force_login(self.admin)
        self.assertFalse(self._fresh(self.admin).is_staff)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_asking_opens_it_for_twelve_hours(self):
        from .models import AdminAccessGrant

        response = self._ask()
        self.assertRedirects(response, reverse("manage_admin_access"))
        grant = AdminAccessGrant.objects.get()
        self.assertEqual((grant.account, grant.reason), (self.admin, "Fix a registration"))
        self.assertEqual(grant.expires_at - grant.started_at, timedelta(hours=12))
        self.assertTrue(self._fresh(self.admin).is_staff)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "access until")

    def test_asking_needs_a_reason_and_the_password(self):
        from .models import AdminAccessGrant

        self.assertContains(self._ask(password="wrong"), "That password isn&#x27;t right.")
        self.assertEqual(self._ask(reason="").status_code, 200)
        self.assertFalse(AdminAccessGrant.objects.exists())

    def test_access_stops_at_twelve_hours_without_the_job(self):
        from .models import AdminAccessGrant

        self._ask()
        AdminAccessGrant.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertTrue(self._fresh(self.admin).is_staff)  # the job hasn't run
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_the_job_closes_it_and_takes_staff_away(self):
        from .admin_access import close_expired
        from .models import AdminAccessGrant

        self._ask()
        expired = timezone.now() - timedelta(minutes=1)
        AdminAccessGrant.objects.update(expires_at=expired)
        self.assertEqual(close_expired(), 1)
        grant = AdminAccessGrant.objects.get()
        self.assertEqual((grant.end_reason, grant.ended_at, grant.ended_by), (AdminAccessGrant.EXPIRED, expired, None))
        self.assertFalse(self._fresh(self.admin).is_staff)
        self.assertEqual(close_expired(), 0)

    def test_ending_early(self):
        from .models import AdminAccessGrant

        self._ask()
        self.assertRedirects(self.client.post(reverse("manage_admin_access_end")), reverse("manage_admin_access"))
        grant = AdminAccessGrant.objects.get()
        self.assertEqual((grant.end_reason, grant.ended_by), (AdminAccessGrant.ENDED, self.admin))
        self.assertFalse(self._fresh(self.admin).is_staff)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_one_open_grant_at_a_time(self):
        from .admin_access import AdminAccessError, request_access

        self._ask()
        with self.assertRaises(AdminAccessError):
            request_access(self._fresh(self.admin), "Again")

    def test_only_organisation_roles_may_ask(self):
        from .admin_access import AdminAccessError, request_access

        parent = User.objects.create(username="parent", email="p@example.com")
        with self.assertRaises(AdminAccessError):
            request_access(parent, "Please")
        self.client.force_login(parent)
        self.assertEqual(self.client.get(reverse("manage_admin_access")).status_code, 404)

    def test_a_superuser_is_never_time_boxed(self):
        root = User.objects.create(username="root", is_superuser=True, is_staff=True)
        self.client.force_login(root)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("manage_admin_access")).status_code, 404)
        from .admin_access import close_expired

        close_expired()
        self.assertTrue(self._fresh(root).is_staff)

    def test_the_other_admins_get_a_notification(self):
        from notifications.models import Notification

        self._ask(reason="Merge two accounts")
        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.other_admin)
        self.assertTrue(notification.organisation)
        self.assertIsNone(notification.dojo)
        self.assertIn("Merge two accounts", notification.text)
        self.assertIn("Ann", notification.text)

    def test_the_request_and_its_end_are_in_the_audit_log(self):
        from auditlog.models import LogEntry

        from .models import AdminAccessGrant

        self._ask()
        self.client.post(reverse("manage_admin_access_end"))
        entries = LogEntry.objects.get_for_object(AdminAccessGrant.objects.get()).order_by("timestamp")
        self.assertEqual(
            [(e.action, e.actor) for e in entries],
            [(LogEntry.Action.CREATE, self.admin), (LogEntry.Action.UPDATE, self.admin)],
        )

    def test_the_page_shows_the_open_access_and_the_history(self):
        self._ask(reason="Fix a registration")
        response = self.client.get(reverse("manage_admin_access"))
        self.assertContains(response, "You have access until")
        self.assertContains(response, reverse("admin:index"))
        self.assertContains(response, "Fix a registration")


class OrganisationNotificationTests(TestCase):
    """The organisation dashboard's notification bell (DATA_MODEL.md §23)."""

    def setUp(self):
        from notifications.services import notify

        from .models import OrganisationRole

        self.admin = User.objects.create(username="admin1", email="a1@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.mine = notify(self.admin, "Someone opened access", url=reverse("manage_admin_access"), organisation=True)
        self.dojo_notice = notify(self.admin, "A personal notice")
        self.client.force_login(self.admin)

    def test_the_bell_shows_only_organisation_notifications(self):
        response = self.client.get(reverse("manage_campaign_list"))
        self.assertContains(response, 'id="notif-admin-page"')
        self.assertContains(response, 'ws-connect="/ws/manage/notifications/"')
        self.assertContains(response, "Someone opened access")
        self.assertNotContains(response, "A personal notice")

    def test_opening_one_marks_it_read_and_follows_it(self):
        url = reverse("open_organisation_notification", kwargs={"notification_id": self.mine.id})
        self.assertRedirects(self.client.get(url), reverse("manage_admin_access"))
        self.mine.refresh_from_db()
        self.assertTrue(self.mine.read)
        other = reverse("open_organisation_notification", kwargs={"notification_id": self.dojo_notice.id})
        self.assertEqual(self.client.get(other).status_code, 404)

    def test_mark_all_read(self):
        response = self.client.post(reverse("mark_all_organisation_notifications_read"))
        self.assertContains(response, 'hx-swap-oob="true"')
        self.mine.refresh_from_db()
        self.dojo_notice.refresh_from_db()
        self.assertEqual((self.mine.read, self.dojo_notice.read), (True, False))

    def test_a_parent_gets_a_404(self):
        self.client.force_login(User.objects.create(username="parent"))
        url = reverse("open_organisation_notification", kwargs={"notification_id": self.mine.id})
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("mark_all_organisation_notifications_read")).status_code, 404)


class OrganisationPeopleTests(TestCase):
    """The People pages (accounts/people.py, accounts.organisation_people,
    DATA_MODEL.md §23): an organisation admin gives and takes away the fixed
    roles, never their own, and the organisation keeps at least one admin."""

    def setUp(self):
        from django.core.management import call_command

        from .models import OrganisationRole

        call_command("load_mail_templates", verbosity=0)
        self.admin = User.objects.create(username="admin1", email="a1@example.com", first_name="Priya")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.person = User.objects.create(username="jan", email="jan@example.com", first_name="Jan")
        self.client.force_login(self.admin)

    def _url(self, account):
        return reverse("manage_person", kwargs={"user_id": account.pk})

    def _save(self, account, *roles):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self._url(account), {"roles": list(roles)})

    def test_the_people_area_is_the_admin_roles(self):
        from .models import OrganisationRole

        reviewer = User.objects.create(username="rev")
        OrganisationRole.objects.create(account=reviewer, role=OrganisationRole.REVIEWER)
        self.client.force_login(reviewer)
        for url in (reverse("manage_people"), reverse("manage_people_add"), self._url(self.person)):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_giving_roles(self):
        from mailing.models import EmailMessage

        from .models import OrganisationRole

        response = self._save(self.person, OrganisationRole.ADMIN, OrganisationRole.REVIEWER)
        self.assertRedirects(response, self._url(self.person))
        self.assertEqual(
            set(self.person.organisation_roles.values_list("role", flat=True)),
            {OrganisationRole.ADMIN, OrganisationRole.REVIEWER},
        )
        person = User.objects.get(pk=self.person.pk)
        self.assertTrue(person.has_perm("accounts.manage_people"))
        self.assertFalse(person.is_staff)
        mail = EmailMessage.objects.get(template_key="organisation_role_changed")
        self.assertEqual(mail.user, self.person)
        self.assertIn("Priya", mail.body)
        response = self.client.get(reverse("manage_people"))
        self.assertContains(response, self._url(self.person))
        self.assertContains(response, "Background-check reviewer")

    def test_taking_the_last_role_away_ends_django_admin_access(self):
        from accounts.testing import with_admin_access

        from .models import AdminAccessGrant, OrganisationRole

        OrganisationRole.objects.create(account=self.person, role=OrganisationRole.BOARD)
        with_admin_access(self.person)
        self._save(self.person)
        self.assertFalse(self.person.organisation_roles.exists())
        self.assertFalse(User.objects.get(pk=self.person.pk).is_staff)
        self.assertEqual(AdminAccessGrant.objects.get().end_reason, AdminAccessGrant.ROLE_REMOVED)

    def test_nobody_changes_their_own_roles(self):
        from .models import OrganisationRole

        OrganisationRole.objects.create(account=self.person, role=OrganisationRole.ADMIN)
        response = self._save(self.admin)
        self.assertTrue(self.admin.organisation_roles.filter(role=OrganisationRole.ADMIN).exists())
        self.assertContains(self.client.get(response.url), "You can&#x27;t change your own roles")

    def test_the_organisation_keeps_an_admin(self):
        from .models import OrganisationRole
        from .organisation_people import OrganisationPeopleError, set_roles

        other = User.objects.create(username="other")
        OrganisationRole.objects.create(account=other, role=OrganisationRole.ADMIN)
        set_roles(self.admin, [], by=other)  # another admin is left
        with self.assertRaises(OrganisationPeopleError):
            set_roles(other, [], by=self.person)

    def test_only_active_adults(self):
        from .organisation_people import OrganisationPeopleError, set_roles

        ninja = User.objects.create(username="kid", account_type=User.NINJA)
        self.assertEqual(self.client.get(self._url(ninja)).status_code, 404)
        service = User.objects.create(username="app", account_type=User.SERVICE)
        for account in (service, User.objects.create(username="gone", is_active=False)):
            with self.assertRaises(OrganisationPeopleError):
                set_roles(account, ["board"], by=self.admin)

    def test_ending_someone_elses_django_admin_access(self):
        from accounts.testing import with_admin_access

        from .models import AdminAccessGrant, OrganisationRole

        OrganisationRole.objects.create(account=self.person, role=OrganisationRole.BOARD)
        with_admin_access(self.person, reason="Check a dojo")
        grant = AdminAccessGrant.objects.get()
        self.assertContains(self.client.get(reverse("manage_people")), "Check a dojo")
        response = self.client.post(reverse("manage_people_end_access", kwargs={"grant_id": grant.pk}))
        self.assertRedirects(response, reverse("manage_people"))
        grant.refresh_from_db()
        self.assertEqual((grant.end_reason, grant.ended_by), (AdminAccessGrant.REVOKED, self.admin))
        self.assertFalse(User.objects.get(pk=self.person.pk).is_staff)

    def test_the_person_page_shows_role_changes_and_access(self):
        from .models import OrganisationRole

        self._save(self.person, OrganisationRole.BOARD)
        self._save(self.person)
        response = self.client.get(self._url(self.person))
        self.assertContains(response, "Board given")
        self.assertContains(response, "Board taken away")
        self.assertContains(response, "Never asked for.")

    def test_finding_an_account(self):
        response = self.client.get(reverse("manage_people_add"), {"q": "jan@"})
        self.assertContains(response, self._url(self.person))

    def test_the_roles_page(self):
        response = self.client.get(reverse("manage_people_roles"))
        self.assertContains(response, "People: organisation roles")
        self.assertContains(response, "Volunteers: background checks, applications")

    def test_superusers_are_listed_but_never_managed_here(self):
        root = User.objects.create(username="root", is_superuser=True, is_staff=True)
        self.assertContains(self.client.get(reverse("manage_people")), "(root)")
        self._save(root, "board")
        root.refresh_from_db()
        self.assertTrue(root.is_superuser and root.is_staff)


class OrganisationInvitationTests(TestCase):
    """Inviting someone without an account to organisation roles
    (accounts.invitations, DATA_MODEL.md §23): they create their own account
    from the link, and only an account with the invited address gets the
    roles."""

    def setUp(self):
        from django.core.cache import cache
        from django.core.management import call_command

        from .models import OrganisationRole

        cache.clear()  # the one-invitation-a-minute throttle
        call_command("load_mail_templates", verbosity=0)
        self.admin = User.objects.create(username="admin1", email="a1@example.com", first_name="Priya")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.client.force_login(self.admin)

    def _invite(self, email="new@example.com", roles=("reviewer",)):
        return self.client.post(
            reverse("manage_people_add"),
            {"name": "Nora New", "email": email, "language": "nl-be", "roles": list(roles)},
        )

    def _token(self):
        import re

        from mailing.models import EmailMessage

        body = EmailMessage.objects.filter(template_key="organisation_invitation").latest("pk").body
        return re.search(r"/invitation/([^/\s]+)/", body).group(1)

    def _link(self, token=None):
        return reverse("organisation_invitation", kwargs={"token": token or self._token()})

    def test_inviting_mails_a_link_to_the_address(self):
        from mailing.models import EmailMessage

        from .models import OrganisationInvitation

        self.assertRedirects(self._invite(), reverse("manage_people"))
        invitation = OrganisationInvitation.objects.get()
        self.assertEqual(
            (invitation.email, invitation.roles, invitation.invited_by), ("new@example.com", ["reviewer"], self.admin)
        )
        mail = EmailMessage.objects.get(template_key="organisation_invitation")
        self.assertEqual((mail.recipient, mail.user, mail.language), ("new@example.com", None, "nl-be"))
        self.assertIn("Nora New", mail.body)
        self.assertNotIn(self._token(), invitation.token_hash)  # only the hash is stored
        self.assertContains(self.client.get(reverse("manage_people")), "new@example.com")

    def test_an_address_with_an_account_gets_roles_from_its_page_instead(self):
        from .models import OrganisationInvitation

        User.objects.create(username="jan", email="New@Example.com")
        self.assertContains(self._invite(), "An account already exists with this email")
        self.assertFalse(OrganisationInvitation.objects.exists())

    def test_one_invitation_a_minute(self):
        self._invite()
        self.assertContains(self._invite(email="other@example.com"), "wait a minute")

    def test_signing_up_from_the_link(self):
        from notifications.models import Notification

        from .models import OrganisationInvitation

        self._invite()
        token = self._token()
        self.client.logout()
        self.assertContains(self.client.get(self._link(token)), "Create my account")
        response = self.client.post(
            reverse("organisation_invitation_sign_up", kwargs={"token": token}),
            {"name": "Nora New", "phone": "", "password": PASSWORD, "preferred_language": "nl-be"},
        )
        self.assertRedirects(response, reverse("manage_home"), fetch_redirect_response=False)
        account = User.objects.get(email="new@example.com")
        self.assertEqual(set(account.organisation_roles.values_list("role", flat=True)), {"reviewer"})
        self.assertEqual(int(self.client.session["_auth_user_id"]), account.pk)
        invitation = OrganisationInvitation.objects.get()
        self.assertEqual(invitation.accepted_by, account)
        notice = Notification.objects.get(recipient=self.admin)
        self.assertTrue(notice.organisation)
        # Used: the link says so, and signs nobody up again.
        self.client.logout()
        self.assertContains(self.client.get(self._link(token)), "isn't valid any more")

    def test_only_the_invited_address_can_accept(self):
        self._invite()
        token = self._token()
        someone = User.objects.create(username="someone", email="someone@example.com")
        self.client.force_login(someone)
        self.assertContains(self.client.get(self._link(token)), "This invitation is for")
        self.assertEqual(self.client.post(self._link(token)).status_code, 404)
        self.assertFalse(someone.organisation_roles.exists())

    def test_an_account_made_since_logs_in_and_accepts(self):
        self._invite()
        token = self._token()
        account = User.objects.create(username="nora", email="NEW@example.com")
        self.client.logout()
        self.assertContains(self.client.get(self._link(token)), "log in with it to accept")
        self.client.force_login(account)
        self.assertRedirects(
            self.client.post(self._link(token)), reverse("manage_home"), fetch_redirect_response=False
        )
        self.assertTrue(account.organisation_roles.filter(role="reviewer").exists())

    def test_resending_replaces_the_link_and_withdrawing_ends_it(self):
        from django.core.cache import cache

        from .models import OrganisationInvitation

        self._invite()
        old = self._token()
        invitation = OrganisationInvitation.objects.get()
        cache.clear()
        self.client.post(reverse("manage_invitation_resend", kwargs={"invitation_id": invitation.pk}))
        new = self._token()
        self.assertNotEqual(old, new)
        self.assertContains(self.client.get(self._link(old)), "isn't valid any more")
        self.client.post(reverse("manage_invitation_withdraw", kwargs={"invitation_id": invitation.pk}))
        self.assertContains(self.client.get(self._link(new)), "isn't valid any more")

    def test_an_expired_link(self):
        from .models import OrganisationInvitation

        self._invite()
        OrganisationInvitation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.client.logout()
        self.assertContains(self.client.get(self._link()), "isn't valid any more")

    def test_old_invitations_are_removed(self):
        from .invitations import remove_old
        from .models import OrganisationInvitation

        self._invite()
        self.assertEqual(remove_old(), 0)
        OrganisationInvitation.objects.update(withdrawn_at=timezone.now() - timedelta(days=31))
        self.assertEqual(remove_old(), 1)

    def test_the_people_area_only(self):
        from .models import OrganisationRole

        reviewer = User.objects.create(username="rev")
        OrganisationRole.objects.create(account=reviewer, role=OrganisationRole.REVIEWER)
        self.client.force_login(reviewer)
        self.assertEqual(self._invite().status_code, 404)


class LoginLinkTestMixin:
    """An account that logs in with an emailed link (accounts/login_links.py,
    DATA_MODEL.md §24), one on a password, and the mail templates loaded."""

    def setUp(self):
        from io import StringIO

        from django.core.cache import cache
        from django.core.management import call_command

        super().setUp()
        cache.clear()  # the test cache (db 3): the one-mail-a-minute throttles
        call_command("load_mail_templates", stdout=StringIO())
        self.user = User.objects.create(
            username="lin", email="lin@example.com", first_name="Lin", login_method=User.LOGIN_LINK
        )
        self.user.set_unusable_password()
        self.user.save()
        self.password_user = User.objects.create(username="pat", email="pat@example.com", first_name="Pat")
        self.password_user.set_password(PASSWORD)
        self.password_user.save()

    def mails(self, key, user=None):
        from mailing.models import EmailMessage

        return EmailMessage.objects.filter(template_key=key, **({"user": user} if user else {}))

    def link_path(self, key="login_link", user=None):
        import re
        from urllib.parse import urlparse

        body = self.mails(key, user).latest("pk").body
        url = urlparse(
            re.search(r"https?://\S+/(?:login/link|account/security/login-method/confirm)/\S+", body).group(0)
        )
        return url.path + (f"?{url.query}" if url.query else "")


class LoginLinkTokenTests(LoginLinkTestMixin, TestCase):
    def test_a_link_works_for_its_account_only_while_valid(self):
        from datetime import datetime

        from . import login_links

        url = login_links.login_url(self.user)
        uid, token = url.rstrip("/").split("/")[-2:]
        self.assertEqual(login_links.user_from_link(uid, token), self.user)
        self.assertIsNone(login_links.user_from_link(uid, token + "x"))
        with patch.object(login_links.LoginLinkTokens, "_now", return_value=datetime.now() + timedelta(minutes=16)):
            self.assertIsNone(login_links.user_from_link(uid, token))

    def test_the_first_link_lasts_days_until_the_first_login(self):
        from datetime import datetime

        from . import login_links

        uid, token = login_links.login_url(self.user, first=True).rstrip("/").split("/")[-2:]
        with patch.object(login_links.FirstLoginLinkTokens, "_now", return_value=datetime.now() + timedelta(days=2)):
            self.assertEqual(login_links.user_from_link(uid, token), self.user)
        self.user.last_login = timezone.now()
        self.user.save()
        self.assertIsNone(login_links.user_from_link(uid, token))

    def test_a_link_stops_working_when_the_address_or_method_changes(self):
        from . import login_links

        uid, token = login_links.login_url(self.user).rstrip("/").split("/")[-2:]
        self.user.email = "lin.new@example.com"
        self.user.save()
        self.assertIsNone(login_links.user_from_link(uid, token))
        uid, token = login_links.login_url(self.user).rstrip("/").split("/")[-2:]
        self.user.login_method = User.LOGIN_PASSWORD
        self.user.save()
        self.assertIsNone(login_links.user_from_link(uid, token))

    def test_never_for_a_password_account_a_switched_off_one_or_a_service_account(self):
        from . import login_links

        for user in (self.password_user,):
            uid, token = login_links.login_url(user).rstrip("/").split("/")[-2:]
            self.assertIsNone(login_links.user_from_link(uid, token))
        uid, token = login_links.login_url(self.user).rstrip("/").split("/")[-2:]
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertIsNone(login_links.user_from_link(uid, token))
        service = User.objects.create(username="svc", account_type=User.SERVICE, login_method=User.LOGIN_LINK)
        uid, token = login_links.login_url(service).rstrip("/").split("/")[-2:]
        self.assertIsNone(login_links.user_from_link(uid, token))


class LoginLinkRequestTests(LoginLinkTestMixin, TestCase):
    """/login/link/: the same answer whatever the address."""

    def ask(self, email):
        return self.client.post(reverse("login_link_request"), {"email": email})

    def test_the_login_page_offers_it(self):
        self.assertContains(self.client.get(reverse("login")), reverse("login_link_request"))

    def test_a_link_account_gets_a_link(self):
        response = self.ask("LIN@example.com")
        self.assertContains(response, "Check your inbox")
        self.assertEqual(self.mails("login_link", self.user).count(), 1)

    def test_the_same_answer_for_a_password_account_and_an_unknown_address(self):
        answers = [self.ask(email) for email in ("lin@example.com", "pat@example.com", "nobody@example.com")]
        self.assertEqual({response.status_code for response in answers}, {200})
        import re

        texts = {
            # The page's card only: with --debug-mode the debug toolbar adds timings.
            re.search(r'<div class="shell login-stage">.*?<a class', response.content.decode(), re.S)
            .group(0)
            .replace(email, "EMAIL")
            for response, email in zip(
                answers, ("lin@example.com", "pat@example.com", "nobody@example.com"), strict=True
            )
        }
        self.assertEqual(len(texts), 1)
        self.assertEqual(self.mails("login_link_not_available", self.password_user).count(), 1)
        self.assertFalse(self.mails("login_link", self.password_user).exists())
        self.assertEqual(self.mails("login_link").count(), 1)

    def test_one_mail_a_minute_per_address(self):
        self.ask("lin@example.com")
        response = self.ask("lin@example.com")
        self.assertContains(response, "Please wait a minute")
        self.assertEqual(self.mails("login_link").count(), 1)
        self.assertContains(self.ask("nobody@example.com"), "Check your inbox")
        self.assertContains(self.ask("nobody@example.com"), "Please wait a minute")

    def test_a_switched_off_account_gets_nothing(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertContains(self.ask("lin@example.com"), "Check your inbox")
        self.assertFalse(self.mails("login_link").exists())

    def test_a_blocked_address_is_suppressed_as_any_mail(self):
        from mailing.models import EmailMessage, EmailSuppression

        EmailSuppression.objects.create(email="lin@example.com", reason=EmailSuppression.MANUAL)
        self.ask("lin@example.com")
        self.assertEqual(self.mails("login_link").get().status, EmailMessage.Status.SUPPRESSED)

    def test_forgot_password_sends_a_link_account_its_login_link(self):
        self.client.post(reverse("password_reset"), {"email": "lin@example.com"})
        self.assertEqual(self.mails("login_link", self.user).count(), 1)
        self.assertFalse(self.mails("password_reset", self.user).exists())
        self.client.post(reverse("password_reset"), {"email": "pat@example.com"})
        self.assertEqual(self.mails("password_reset", self.password_user).count(), 1)


class LoginLinkLoginTests(LoginLinkTestMixin, TwoStepTestMixin, TestCase):
    """/login/link/<uidb64>/<token>/: GET asks, POST logs in, then the second
    step as on /login/."""

    def link(self, next_url=None):
        from . import login_links

        url = login_links.login_url(self.user, next_url)
        return url.removeprefix(settings_site_url())

    def test_get_asks_and_logs_nothing_in(self):
        response = self.client.get(self.link())
        self.assertContains(response, "Log in as")
        self.assertContains(response, "lin@example.com")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_post_logs_in_once(self):
        from core.testing import link_login_data

        link = self.link()
        response = self.client.post(link, link_login_data())
        self.assertRedirects(response, reverse("account_home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.client.logout()
        response = self.client.post(link, link_login_data())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.get(link), "Email me a new login link")

    def test_the_link_from_the_request_page_works(self):
        from core.testing import link_login_data

        self.client.post(reverse("login_link_request"), {"email": "lin@example.com", "next": "/account/mail/"})
        link = self.link_path()
        self.assertIn("next=", link)
        response = self.client.post(link, link_login_data())
        self.assertRedirects(response, "/account/mail/", fetch_redirect_response=False)

    def test_a_link_account_cannot_log_in_with_a_password(self):
        response = self.client.post(reverse("login"), login_data("lin@example.com", PASSWORD))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_two_step_login_still_follows(self):
        from django_otp import DEVICE_ID_SESSION_KEY

        from core.testing import link_login_data, token_data, totp_code

        device = self.add_app(self.user)
        link = self.link()
        response = self.client.post(link, link_login_data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["wizard"]["steps"].current, "token")
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(link, token_data(totp_code(device), view="login_link_view"))
        self.assertRedirects(response, reverse("account_home"))
        self.assertEqual(self.client.session[DEVICE_ID_SESSION_KEY], device.persistent_id)

    def test_the_policy_still_applies_after_a_link_login(self):
        from accounts.models import SignInRequirement
        from core.testing import link_login_data

        SignInRequirement.objects.create(role=SignInRequirement.ADULT, level=SignInRequirement.TWO_STEP)
        self.client.post(self.link(), link_login_data())
        response = self.client.get(reverse("account_home"))
        self.assertRedirects(response, reverse("account_security"), fetch_redirect_response=False)


class LoginMethodSwitchTests(LoginLinkTestMixin, TestCase):
    """Choosing on Sign-in security: to a link (confirmed from the mailbox)
    and back to a password (DATA_MODEL.md §24)."""

    def test_the_security_page_shows_the_method(self):
        self.client.force_login(self.password_user)
        response = self.client.get(reverse("account_security"))
        self.assertContains(response, "Switch to a login link")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("account_security")), "Use a password instead")

    def test_switching_to_a_link_needs_the_password_then_the_mailbox(self):
        self.client.force_login(self.password_user)
        response = self.client.post(reverse("account_login_method"), {"password": "wrong"})
        self.assertFalse(self.mails("login_method_confirm").exists())
        response = self.client.post(reverse("account_login_method"), {"password": PASSWORD})
        self.assertContains(response, "pat@example.com")
        self.password_user.refresh_from_db()
        self.assertEqual(self.password_user.login_method, User.LOGIN_PASSWORD)
        self.assertTrue(self.password_user.check_password(PASSWORD))

        link = self.link_path("login_method_confirm", self.password_user)
        self.assertContains(self.client.get(link), "Yes, log in with a link")
        self.password_user.refresh_from_db()
        self.assertEqual(self.password_user.login_method, User.LOGIN_PASSWORD)

        response = self.client.post(link)
        self.assertRedirects(response, reverse("account_security"))
        self.password_user.refresh_from_db()
        self.assertEqual(self.password_user.login_method, User.LOGIN_LINK)
        self.assertFalse(self.password_user.has_usable_password())
        # This session stays; the mail tells the account.
        self.assertEqual(self.client.get(reverse("account_home")).status_code, 200)
        self.assertEqual(self.mails("login_method_changed", self.password_user).count(), 1)
        # Used once.
        self.assertEqual(self.client.get(link).status_code, 400)

    def test_the_switch_ends_the_other_sessions(self):
        from django.test import Client

        other = Client()
        other.force_login(self.password_user)
        self.client.force_login(self.password_user)
        self.client.post(reverse("account_login_method"), {"password": PASSWORD})
        self.client.post(self.link_path("login_method_confirm", self.password_user))
        self.assertEqual(other.get(reverse("account_home")).status_code, 302)

    def test_the_confirmation_works_logged_out_but_not_for_another_account(self):
        self.client.force_login(self.password_user)
        self.client.post(reverse("account_login_method"), {"password": PASSWORD})
        link = self.link_path("login_method_confirm", self.password_user)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(link).status_code, 404)
        self.client.logout()
        response = self.client.post(link)
        self.assertContains(response, "Log in with a link")
        self.password_user.refresh_from_db()
        self.assertTrue(self.password_user.uses_login_link)

    def test_back_to_a_password_needs_a_recent_login(self):
        from . import reauth

        self.client.force_login(self.user)  # force_login sends user_logged_in: recent
        response = self.client.post(
            reverse("account_security_password"), {"new_password1": PASSWORD, "new_password2": PASSWORD}
        )
        self.assertRedirects(response, reverse("account_security"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_method, User.LOGIN_PASSWORD)
        self.assertTrue(self.user.check_password(PASSWORD))
        self.assertEqual(self.mails("login_method_changed", self.user).count(), 1)

        self.user.login_method = User.LOGIN_LINK
        self.user.set_unusable_password()
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session[reauth.LOGIN_AT_SESSION] -= (reauth.RECENT_MINUTES + 1) * 60
        session.save()
        response = self.client.post(
            reverse("account_security_password"), {"new_password1": PASSWORD, "new_password2": PASSWORD}
        )
        self.assertContains(response, "Mail me a confirmation link")
        self.user.refresh_from_db()
        self.assertTrue(self.user.uses_login_link)

    def test_change_password_sends_a_link_account_to_set_one(self):
        self.client.force_login(self.user)
        self.assertRedirects(
            self.client.get(reverse("change_password")),
            reverse("account_security_password"),
            fetch_redirect_response=False,
        )

    def test_the_switch_is_in_the_audit_log(self):
        from auditlog.models import LogEntry

        self.client.force_login(self.password_user)
        self.client.post(reverse("account_login_method"), {"password": PASSWORD})
        self.client.post(self.link_path("login_method_confirm", self.password_user))
        entry = LogEntry.objects.get_for_object(self.password_user).latest("timestamp")
        self.assertIn("login_method", entry.changes_dict)
        self.assertEqual(entry.actor, self.password_user)


class ConfirmIdentityWithoutPasswordTests(LoginLinkTestMixin, TwoStepTestMixin, TestCase):
    """The pages that ask for the password accept a recent login from an
    account on a link, and otherwise offer a link back (accounts.reauth)."""

    def make_old(self):
        from . import reauth

        session = self.client.session
        session[reauth.LOGIN_AT_SESSION] -= (reauth.RECENT_MINUTES + 1) * 60
        session.save()

    def test_turning_off_two_step_login(self):
        from core.testing import login_verified

        login_verified(self.client, self.user)
        self.make_old()
        response = self.client.post(reverse("account_security_turn_off"), {})
        self.assertContains(response, "Mail me a confirmation link")
        self.assertTrue(self.user.totpdevice_set.exists())
        login_verified(self.client, self.user)  # a fresh login
        self.client.post(reverse("account_security_turn_off"), {})
        self.assertFalse(self.user.totpdevice_set.exists())

    def test_deleting_the_account(self):
        self.client.force_login(self.user)
        self.make_old()
        response = self.client.post(reverse("delete_my_account"), {})
        self.assertContains(response, "Mail me a confirmation link")
        self.assertTrue(User.objects.filter(pk=self.user.pk, is_active=True).exists())
        self.client.force_login(self.user)
        self.client.post(reverse("delete_my_account"), {})
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, "lin@example.com")

    def test_changing_the_email_address(self):
        self.client.force_login(self.user)
        self.make_old()
        self.client.post(reverse("change_email"), {"new_email": "lin.new@example.com"})
        self.assertFalse(self.mails("email_change_confirm").exists())
        self.client.force_login(self.user)
        self.client.post(reverse("change_email"), {"new_email": "lin.new@example.com"})
        self.assertTrue(self.mails("email_change_confirm").exists())

    def test_a_password_account_still_needs_its_password(self):
        self.client.force_login(self.password_user)
        response = self.client.get(reverse("change_email"))
        self.assertContains(response, 'name="password"')
        self.assertNotContains(response, "Mail me a confirmation link")

    def test_the_confirmation_link_brings_them_back(self):
        from core.testing import link_login_data

        self.client.force_login(self.user)
        self.make_old()
        response = self.client.post(reverse("login_link_reauth"), {"next": reverse("change_email")})
        self.assertContains(response, "lin@example.com")
        link = self.link_path()
        response = self.client.post(link, link_login_data())
        self.assertRedirects(response, reverse("change_email"), fetch_redirect_response=False)
        form = self.client.get(reverse("change_email")).context["form"]
        self.assertTrue(form.recent)

    def test_the_confirmation_link_never_leaves_the_site(self):
        self.client.force_login(self.user)
        self.client.post(reverse("login_link_reauth"), {"next": "https://evil.example.com/"})
        self.assertNotIn("evil", self.link_path())


class SignUpWithLoginLinkTests(LoginLinkTestMixin, TestCase):
    """Choosing a login link at sign-up (DATA_MODEL.md §24)."""

    def family_data(self, **overrides):
        return {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "",
            "consent": "on",
            **CHILD_ROWS,
            "child-0-name": "Sam",
            "child-0-family_name": "Peeters",
            "child-0-date_of_birth": _dob(10),
            "child-0-allergies_notes": "",
            **overrides,
        }

    def test_the_page_offers_the_choice(self):
        self.assertContains(self.client.get(reverse("register_guardian")), "How do you want to log in?")

    def test_a_password_is_still_needed_when_it_is_chosen(self):
        response = self.client.post(reverse("register_guardian"), self.family_data(login_method="password"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["password"])
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_a_family_on_a_link_confirms_the_address_with_its_first_login(self):
        from core.testing import link_login_data

        response = self.client.post(
            reverse("register_guardian"), self.family_data(login_method="link", password="ignored")
        )
        self.assertContains(response, "Check your inbox")
        jane = User.objects.get(email="jane@example.com")
        self.assertTrue(jane.uses_login_link)
        self.assertFalse(jane.has_usable_password())
        self.assertEqual(list(Ninja.objects.of_guardian(jane).values_list("name", flat=True)), ["Sam"])
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(self.mails("login_link", jane).get().subject.startswith("Welcome"))
        link = self.link_path(user=jane)
        response = self.client.post(link, link_login_data())
        self.assertRedirects(response, reverse("account_home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), jane.pk)
        self.client.logout()
        self.assertContains(self.client.get(link), "Email me a new login link")  # the first link is used up

    def test_the_first_link_returns_to_the_event_sign_up(self):
        from core.testing import link_login_data

        self.client.post(
            reverse("register_guardian"),
            self.family_data(login_method="link", next="/events/7/signup/"),
        )
        jane = User.objects.get(email="jane@example.com")
        response = self.client.post(self.link_path(user=jane), link_login_data())
        self.assertRedirects(response, "/events/7/signup/", fetch_redirect_response=False)

    def test_sign_up_without_children_on_a_link(self):
        from core.testing import link_login_data

        response = self.client.post(
            reverse("register_individual"),
            {"name": "Jo Smit", "email": "jo@example.com", "login_method": "link", "next": reverse("register_helper")},
        )
        self.assertContains(response, "Check your inbox")
        jo = User.objects.get(email="jo@example.com")
        self.assertTrue(jo.uses_login_link)
        response = self.client.post(self.link_path(user=jo), link_login_data())
        self.assertRedirects(response, reverse("register_helper"), fetch_redirect_response=False)

    def test_an_invited_account_on_a_link_logs_in_straight_away(self):
        from .invitations import invite

        admin = User.objects.create(username="boss", email="boss@example.com")
        from .models import OrganisationRole

        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        with patch("accounts.invitations.secrets.token_urlsafe", return_value="tok-123"):
            invite("new@example.com", "Nora New", ["reviewer"], admin, "en-us")
        response = self.client.post(
            reverse("organisation_invitation_sign_up", kwargs={"token": "tok-123"}),
            {"name": "Nora New", "phone": "", "login_method": "link", "preferred_language": "nl-be"},
        )
        self.assertRedirects(response, reverse("manage_home"), fetch_redirect_response=False)
        nora = User.objects.get(email="new@example.com")
        self.assertTrue(nora.uses_login_link)
        self.assertFalse(nora.has_usable_password())
        self.assertEqual(int(self.client.session["_auth_user_id"]), nora.pk)


class NinjaLoginOptionsTests(LoginLinkTestMixin, TwoStepTestMixin, TestCase):
    """A child's own login has the same options as an adult's, and the
    guardian helps with it from the Own login card (DATA_MODEL.md §24)."""

    def setUp(self):
        super().setUp()
        self.guardian = User.objects.create(username="ellen", email="ellen@example.com", first_name="Ellen")
        self.guardian.set_password(PASSWORD)
        self.guardian.save()
        self.child = make_ninja(self.guardian, "Emma", date_of_birth=_dob(12))
        self.client.force_login(self.guardian)

    def url(self, name):
        return reverse(name, kwargs={"ninja_id": self.child.id})

    def give(self, login_method):
        self.client.post(self.url("ninja_login_create"), {"email": "emma@example.com", "login_method": login_method})
        self.child.refresh_from_db()
        return self.child.account

    def test_a_guardian_gives_a_login_on_a_link(self):
        from core.testing import link_login_data

        account = self.give("link")
        self.assertTrue(account.uses_login_link)
        self.assertFalse(account.has_usable_password())
        mail = self.mails("ninja_account_created", account).get()
        self.assertIn("/login/link/", mail.body)
        self.assertContains(self.client.get(self.url("ninja_detail")), "Send the login mail again")

        self.client.logout()
        link = self.link_path("ninja_account_created", account)
        response = self.client.post(link, link_login_data())
        self.assertRedirects(response, self.url("ninja_detail"))
        # The child can ask for the next link itself.
        self.client.logout()
        self.client.post(reverse("login_link_request"), {"email": "emma@example.com"})
        self.assertEqual(self.mails("login_link", account).count(), 1)

    def test_a_ninja_login_sets_up_two_step_login_and_the_family_hears_of_it(self):
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        from accounts import two_step

        account = self.give("password")
        device = self.add_app(account)
        request = RequestFactory().post("/")
        request.user, request.session = account, SessionStore()
        two_step._added(request, device)
        self.assertEqual(self.mails("two_step_turned_on", account).count(), 1)
        notice = self.mails("child_login_changed", self.guardian).get()
        self.assertIn("Emma turned on two-step login", notice.body)

    def test_the_guardian_turns_off_the_childs_two_step_login(self):
        account = self.give("password")
        self.add_app(account)
        self.assertContains(self.client.get(self.url("ninja_detail")), "Two-step login is on")
        response = self.client.post(self.url("ninja_login_two_step_off"), {"password": "wrong"})
        self.assertTrue(account.totpdevice_set.exists())
        response = self.client.post(self.url("ninja_login_two_step_off"), {"password": PASSWORD})
        self.assertRedirects(response, self.url("ninja_detail"))
        self.assertFalse(account.totpdevice_set.exists())
        mail = self.mails("two_step_turned_off", account).get()
        self.assertIn("Ellen turned off two-step login", mail.body)
        self.assertIn(
            "Two-step login was turned off for Emma", self.mails("child_login_changed", self.guardian).get().body
        )

    def test_the_guardian_switches_the_child_back_to_a_password(self):
        account = self.give("link")
        response = self.client.post(self.url("ninja_login_use_password"), {"password": PASSWORD})
        self.assertRedirects(response, self.url("ninja_detail"))
        account.refresh_from_db()
        self.assertEqual(account.login_method, User.LOGIN_PASSWORD)
        self.assertFalse(account.has_usable_password())
        self.assertIn("/password-reset/confirm/", self.mails("ninja_account_created", account).latest("pk").body)
        self.assertIn("switched your CoderDojo login back", self.mails("login_method_changed", account).get().body)

    def test_the_child_switches_itself_to_a_link(self):
        account = self.give("password")
        account.set_password(PASSWORD)
        account.save()
        self.client.force_login(account)
        self.client.post(reverse("account_login_method"), {"password": PASSWORD})
        self.client.post(self.link_path("login_method_confirm", account))
        account.refresh_from_db()
        self.assertTrue(account.uses_login_link)
        self.assertIn("Emma now logs in with a link", self.mails("child_login_changed", self.guardian).get().body)

    def test_only_the_childs_guardians(self):
        self.give("link")
        stranger = User.objects.create(username="stranger", email="stranger@example.com")
        self.client.force_login(stranger)
        for name in ("ninja_login_two_step_off", "ninja_login_use_password", "ninja_login_email"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 404)
        self.client.force_login(self.child.account)
        for name in ("ninja_login_two_step_off", "ninja_login_use_password", "ninja_login_email"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 404)

    def test_the_policy_never_requires_anything_of_a_ninja_login(self):
        from accounts.models import SignInRequirement

        account = self.give("password")
        SignInRequirement.objects.create(role=SignInRequirement.ADULT, level=SignInRequirement.TWO_STEP)
        self.client.force_login(account)
        self.assertEqual(self.client.get(self.url("ninja_detail")).status_code, 200)


class GuardianChangesChildAddressTests(LoginLinkTestMixin, TestCase):
    """The guardian changes the address of their child's login, through the
    confirmed email change (accounts.email_change, DATA_MODEL.md §24)."""

    def setUp(self):
        super().setUp()
        self.guardian = User.objects.create(username="ellen", email="ellen@example.com", first_name="Ellen")
        self.guardian.set_password(PASSWORD)
        self.guardian.save()
        self.second = User.objects.create(username="bram", email="bram@example.com", first_name="Bram")
        self.second.set_password(PASSWORD)
        self.second.save()
        self.account = User.objects.create(username="emma", email="emma@example.com", account_type=User.NINJA)
        self.child = make_ninja(self.guardian, "Emma", account=self.account)
        Guardianship.objects.create(guardian=self.second, ninja=self.child)
        self.client.force_login(self.guardian)

    def url(self):
        return reverse("ninja_login_email", kwargs={"ninja_id": self.child.id})

    def ask(self, new_email="emma.new@example.com", password=PASSWORD):
        return self.client.post(self.url(), {"new_email": new_email, "password": password})

    def confirm_path(self):
        import re
        from urllib.parse import urlparse

        body = self.mails("email_change_confirm").latest("pk").body
        return urlparse(re.search(r"\S+/account/email/confirm/\S+", body).group(0)).path

    def test_the_link_goes_to_the_new_address_and_works_logged_out(self):
        from auditlog.models import LogEntry

        response = self.ask()
        self.assertRedirects(response, reverse("ninja_detail", kwargs={"ninja_id": self.child.id}))
        mail = self.mails("email_change_confirm").get()
        self.assertEqual(mail.recipient, "emma.new@example.com")
        self.assertIn("Ellen is changing the email address", mail.body)
        self.account.refresh_from_db()
        self.assertEqual(self.account.email, "emma@example.com")

        self.client.logout()
        path = self.confirm_path()
        self.client.post(path)
        self.account.refresh_from_db()
        self.assertEqual(self.account.email, "emma.new@example.com")
        self.assertEqual(self.mails("email_changed", self.account).get().recipient, "emma@example.com")
        notices = self.mails("child_login_changed")
        self.assertEqual({notice.user for notice in notices}, {self.guardian, self.second})
        self.assertIn("emma.new@example.com", notices.first().body)
        entry = LogEntry.objects.get_for_object(self.account).latest("timestamp")
        self.assertEqual(entry.actor, self.guardian)

    def test_needs_the_guardians_password(self):
        self.ask(password="wrong")
        self.assertFalse(self.mails("email_change_confirm").exists())

    def test_a_second_guardian_can_start_it(self):
        self.client.force_login(self.second)
        self.ask()
        self.assertIn("Bram is changing", self.mails("email_change_confirm").get().body)

    def test_refused_once_the_starter_is_no_longer_a_guardian(self):
        self.ask()
        Guardianship.objects.filter(guardian=self.guardian).delete()
        self.client.logout()
        response = self.client.post(self.confirm_path())
        self.assertEqual(response.status_code, 400)
        self.account.refresh_from_db()
        self.assertEqual(self.account.email, "emma@example.com")

    def test_a_taken_address_is_refused(self):
        response = self.ask(new_email="bram@example.com")
        self.assertContains(response, "An account already exists with this email.")

    def test_the_childs_other_sessions_end(self):
        from django.test import Client

        child_client = Client()
        child_client.force_login(self.account)
        self.ask()
        self.client.logout()
        self.client.post(self.confirm_path())
        self.assertEqual(
            child_client.get(reverse("ninja_detail", kwargs={"ninja_id": self.child.id})).status_code, 302
        )

    def test_the_organisation_still_cannot_change_a_ninja_login(self):
        from .email_change import EmailChangeError, request_change

        admin = User.objects.create(username="boss", email="boss@example.com")
        with self.assertRaises(EmailChangeError):
            request_change(self.account, "emma.new@example.com", started_by=admin)


class SeedLoginLinksTests(TestCase):
    """seed_login_links and the credentials file's note for those accounts."""

    def test_switches_a_parent_and_a_mentor_but_never_the_two_step_picks(self):
        from io import StringIO

        from django.core.management import call_command

        from .seed_credentials import LOGIN_LINK_PASSWORD, describe_account, describe_rows

        dojo = make_dojo("Dojo Test", champion=User.objects.create(username="champ", email="c@coderdojo-demo.example"))
        mentors = [User.objects.create(username=f"mentor-{i}", email=f"m{i}@coderdojo-demo.example") for i in (1, 2)]
        for mentor in mentors:
            add_member(dojo, mentor, DojoMembership.MENTOR)
        parents = [User.objects.create(username=f"parent-{i}", email=f"p{i}@coderdojo-demo.example") for i in (1, 2)]
        for parent in parents:
            make_ninja(parent, "Kid")
        outsider = User.objects.create(username="real", email="real@example.com")
        make_ninja(outsider, "Other")
        call_command("seed_two_step", stdout=StringIO())
        call_command("seed_login_links", stdout=StringIO())
        switched = set(User.objects.filter(login_method=User.LOGIN_LINK).values_list("username", flat=True))
        self.assertEqual(switched, {"mentor-2", "parent-2"})
        self.assertFalse(User.objects.get(username="parent-2").has_usable_password())
        call_command("seed_login_links", stdout=StringIO())  # rerun-safe
        self.assertEqual(User.objects.filter(login_method=User.LOGIN_LINK).count(), 2)

        parent = User.objects.get(username="parent-2")
        self.assertIn("LOGIN LINK", describe_account(parent))
        row = describe_rows([{"role": "guardian", "username": "parent-2", "email": parent.email, "password": "x"}])[0]
        self.assertEqual((row["role"], row["password"]), ("guardian", LOGIN_LINK_PASSWORD))


class ChildLoginWithoutEmailTests(LoginLinkTestMixin, TestCase):
    """A child login without an email address (older seeded data): the card
    says so instead of leaving a gap, and offers to add one."""

    def test_the_card_offers_to_add_an_address(self):
        guardian = User.objects.create(username="ellen", email="ellen@example.com")
        guardian.set_password(PASSWORD)
        guardian.save()
        account = User.objects.create(username="finn-login", email="", account_type=User.NINJA)
        child = make_ninja(guardian, "Finn", account=account)
        self.client.force_login(guardian)
        response = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": child.id}))
        self.assertContains(response, "logs in with the username <strong>finn-login</strong>")
        self.assertNotContains(response, "logs in with <strong></strong>")
        self.assertContains(response, "Add an email address")

        self.client.post(
            reverse("ninja_login_email", kwargs={"ninja_id": child.id}),
            {"new_email": "finn@example.com", "password": PASSWORD},
        )
        self.assertEqual(self.mails("email_change_confirm").get().recipient, "finn@example.com")


def settings_site_url():
    from django.conf import settings

    return settings.SITE_URL


class AccountNavigationCacheTests(TestCase):
    """accounts.navigation: what the nav shows about an account is cached
    per account and follows every change to it, and never opens anything."""

    def setUp(self):
        from dojos.testing import make_champion

        self.user = make_champion(username="nav", email="nav@example.com")
        self.client.force_login(self.user)

    def _nav(self):
        return self.client.get(reverse("contact")).context

    def test_a_second_page_reads_it_from_the_cache(self):
        from . import navigation

        navigation.clear(self.user.pk)
        self._nav()
        with patch.object(navigation, "build", side_effect=AssertionError("built again")):
            self.assertTrue(self._nav()["user_is_approved_champion"])

    def test_a_new_dojo_shows_in_the_nav_and_the_switcher_at_once(self):
        from dojos.testing import make_dojo

        self.assertFalse(self._nav()["user_can_manage"])
        dojo = make_dojo("Ghent", champion=self.user)
        context = self._nav()
        self.assertEqual(context["user_admin_dojo"], dojo)
        self.assertTrue(context["user_can_manage"])
        dojo.name = "Gent"
        dojo.save()
        self.assertEqual(self._nav()["user_admin_dojo"].name, "Gent")

    def test_an_organisation_role_shows_at_once(self):
        from .models import OrganisationRole

        self.assertFalse(self._nav()["user_is_organisation_admin"])
        OrganisationRole.objects.create(account=self.user, role=OrganisationRole.ADMIN)
        self.assertTrue(self._nav()["user_is_organisation_admin"])

    def test_a_lapsed_check_changes_it_without_any_save(self):
        from dojos.testing import make_dojo

        make_dojo("Ghent", champion=self.user)
        self.assertIsNotNone(self._nav()["user_admin_dojo"])
        User.objects.filter(pk=self.user.pk).update(background_check_expires_at=timezone.now() - timedelta(days=1))
        context = self._nav()
        self.assertIsNone(context["user_admin_dojo"])
        self.assertFalse(context["user_is_approved_champion"])

    def test_a_stale_nav_never_opens_a_page(self):
        """Access checks ask the database: a membership ended behind the
        cache's back (QuerySet.update sends no signal) still closes the dojo."""
        from dojos.models import DojoMembership
        from dojos.testing import make_dojo

        dojo = make_dojo("Ghent", champion=self.user)
        self.assertIsNotNone(self._nav()["user_admin_dojo"])
        DojoMembership.objects.filter(dojo=dojo).update(status=DojoMembership.DORMANT)
        self.assertIsNotNone(self._nav()["user_admin_dojo"])  # the nav is stale for a while
        self.assertEqual(self.client.get(reverse("dojo_dashboard", args=[dojo.id])).status_code, 404)


class SignInPolicyCacheTests(TestCase):
    """accounts.sign_in.policy: cached, and a change applies at once."""

    def setUp(self):
        from . import sign_in

        sign_in.clear_policy_cache()
        self.addCleanup(sign_in.clear_policy_cache)
        self.user = User.objects.create(username="pol", email="pol@example.com")

    def test_it_is_read_once_and_a_new_requirement_applies_at_once(self):
        from . import sign_in
        from .models import SignInRequirement

        sign_in.requirements_for(self.user)
        with self.assertNumQueries(0):
            enforced, _upcoming = sign_in.requirements_for(self.user)
        self.assertEqual(enforced.level, sign_in.PASSWORD)
        requirement = SignInRequirement.objects.create(role=SignInRequirement.ADULT, level=SignInRequirement.TWO_STEP)
        self.assertEqual(sign_in.requirements_for(self.user)[0].level, sign_in.TWO_STEP)
        requirement.delete()
        self.assertEqual(sign_in.requirements_for(self.user)[0].level, sign_in.PASSWORD)


class CachedSessionTests(TestCase):
    """Sessions are read from the cache and kept in the database too
    (settings.SESSION_ENGINE): an emptied cache logs nobody out."""

    def test_a_session_survives_an_emptied_cache(self):
        from django.contrib.sessions.models import Session
        from django.core.cache import cache

        user = User.objects.create(username="sess", email="sess@example.com")
        self.client.force_login(user)
        self.assertTrue(Session.objects.filter(session_key=self.client.session.session_key).exists())
        cache.clear()
        self.assertEqual(self.client.get(reverse("account_home")).status_code, 200)
