from datetime import timedelta
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from applications.models import Application
from core.testing import TempMediaMixin
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
        response = self.client.post(reverse("login"), {"email": self.guardian.email, "password": PASSWORD})
        self.assertRedirects(response, reverse("account_home"))

    def test_valid_login_by_username(self):
        """EmailOrUsernameBackend accepts either — seeded demo accounts are
        keyed by username."""
        response = self.client.post(reverse("login"), {"email": self.guardian.username, "password": PASSWORD})
        self.assertRedirects(response, reverse("account_home"))

    def test_invalid_password_shows_error(self):
        response = self.client.post(reverse("login"), {"email": self.guardian.email, "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["error"])

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
        response = self.client.post(reverse("add_ninja"), {"consent": "on", "name": "Kid"})
        self.assertEqual(response.status_code, 302)

    def test_the_consent_is_optional_and_recorded(self):
        from accounts.consent import CHILD_DATA_WORDING_VERSION

        self.client.force_login(self.guardian)
        self.client.post(reverse("add_ninja"), {"name": "No Consent", "date_of_birth": _dob(10)})
        guardianship = Guardianship.objects.get(ninja__name="No Consent")
        self.assertIsNone(guardianship.consent_given_at)

        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "Consented", "date_of_birth": _dob(10)})
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
            {"consent": "on", "name": "New Kid", "date_of_birth": _dob(10)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Ninja.objects.of_guardian(self.guardian).filter(name="New Kid").exists())

    def test_picked_icon_links_the_standard_avatar(self):
        self.client.force_login(self.guardian)
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "A", "date_of_birth": _dob(10), "icon": "alien-01-green.svg"})
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "B", "date_of_birth": _dob(10), "icon": "alien-01-green.svg"})
        photos = set(Ninja.objects.of_guardian(self.guardian).values_list("photo", flat=True))
        self.assertEqual(photos, {"library/ninjas/alien-01-green.svg"})
        self.assertFalse((self.media_root / "participants").exists())

    def test_unknown_icon_is_ignored(self):
        self.client.force_login(self.guardian)
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "A", "date_of_birth": _dob(10), "icon": "../../settings.py"})
        self.assertFalse(Ninja.objects.get(name="A").photo)

    def test_any_adult_account_can_add_children(self):
        """No separate "guardian" role any more — e.g. a dojo owner adds
        their own child from their account page directly."""
        owner = make_champion(username="owner1")
        self.client.force_login(owner)
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "Owner Kid"})
        self.assertEqual(list(Ninja.objects.of_guardian(owner).values_list("name", flat=True)), ["Owner Kid"])

    def test_ninja_login_cannot_add_children(self):
        ninja_login = User.objects.create(username="kid", account_type=User.NINJA)
        self.client.force_login(ninja_login)
        response = self.client.post(reverse("add_ninja"), {"consent": "on", "name": "Nope"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Ninja.objects.exists())

    def test_blank_name_creates_nothing(self):
        self.client.force_login(self.guardian)
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "  "})
        self.assertEqual(Ninja.objects.of_guardian(self.guardian).count(), 0)

    def test_gender_is_saved_and_optional(self):
        self.client.force_login(self.guardian)
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "A", "gender": Ninja.GIRL})
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "B"})
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "C", "gender": "dragon"})
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
        response = self.client.get(
            reverse("ninja_detail", kwargs={"ninja_id": self.child.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_another_familys_child_is_404(self):
        self.client.force_login(self.guardian)
        response = self.client.get(
            reverse("ninja_detail", kwargs={"ninja_id": self.other_child.id})
        )
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
        response = self.client.get(
            reverse("edit_ninja", kwargs={"ninja_id": self.child.id})
        )
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

    def test_edit_form_preselects_the_gender(self):
        Ninja.objects.filter(pk=self.child.pk).update(gender=Ninja.OTHER)
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("edit_ninja", kwargs={"ninja_id": self.child.id}))
        self.assertContains(response, '<option value="other" selected>')


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
        response = self.client.post(
            reverse(
                "cancel_registration", kwargs={"registration_id": self.confirmed.id}
            )
        )
        self.assertRedirects(response, reverse("account_home"))
        self.assertFalse(Registration.objects.filter(id=self.confirmed.id).exists())
        self.waitlisted.refresh_from_db()
        self.assertFalse(self.waitlisted.waiting_list)

    def test_cannot_cancel_another_familys_registration(self):
        other_guardian = User.objects.create(username="g2", email="g2@example.com")
        self.client.force_login(other_guardian)
        response = self.client.post(
            reverse(
                "cancel_registration", kwargs={"registration_id": self.confirmed.id}
            )
        )
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
            name="Antwerp Session", dojo=dojo,
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=1,
        )
        confirmed = Registration.objects.create(event=event, ninja=self.child, waiting_list=False, position=1)
        Registration.objects.create(event=event, ninja=self.waitlisted_child, waiting_list=True, position=2)
        self.client.force_login(self.guardian)

        with patch("dojos.team.notify") as mock_notify:
            self.client.post(
                reverse("cancel_registration", kwargs={"registration_id": confirmed.id})
            )

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
                    "cancel_registration", kwargs={"registration_id": self.confirmed.id},
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
            "child_1_name": "Sam",
            "child_1_dob": _dob(10),
            "child_1_notes": "",
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
        self.assertEqual(len(response.context["child_rows"]), 1)

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
            child_3_name="Alex", child_3_dob=_dob(12), child_3_notes="Peanut allergy",
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
        data = self._valid_post_data(child_1_gender=Ninja.GIRL, child_2_name="Alex", child_2_dob=_dob(9))
        self.client.post(reverse("register_guardian"), data)

        guardian = User.objects.get(email="jane@example.com")
        genders = dict(Ninja.objects.of_guardian(guardian).values_list("name", "gender"))
        self.assertEqual(genders, {"Sam": Ninja.GIRL, "Alex": Ninja.UNSPECIFIED})

    def test_form_offers_the_gender_choices(self):
        response = self.client.get(reverse("register_guardian"))
        self.assertContains(response, 'name="child_1_gender"')
        self.assertContains(response, 'id="rp-gender-choices"')

    def test_postcode_and_mail_language_are_saved(self):
        Municipality.objects.create(postal_code="9000", name="Gent", center=Point(3.7174, 51.0543, srid=4326))
        self.client.post(reverse("register_guardian"), self._valid_post_data(postal_code="9000", preferred_language="fr-be"))

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
            reverse("register_guardian"), self._valid_post_data(child_1_name="", child_1_dob="")
        )

        self.assertEqual(response.status_code, 200)
        row = response.context["child_rows"][0]
        self.assertIn("name", row["errors"])
        self.assertIn("dob", row["errors"])
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())
        self.assertFalse(Ninja.objects.exists())

    def test_no_children_is_rejected(self):
        data = self._valid_post_data()
        del data["child_1_name"]
        del data["child_1_dob"]
        del data["child_1_notes"]

        response = self.client.post(reverse("register_guardian"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["children_error"])
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())


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
                user = User(username=status, background_check_status=status,
                            background_check_expires_at=timezone.now() + timedelta(days=1))
                self.assertFalse(user.background_check_valid)

    def test_invalid_when_validated_but_expired(self):
        user = self._user(background_check_status=User.CHECK_VALIDATED,
                          background_check_expires_at=timezone.now() - timedelta(days=1))
        self.assertFalse(user.background_check_valid)
        self.assertTrue(user.background_check_can_upload)

    def test_valid_when_validated_and_not_expired(self):
        user = self._user(background_check_status=User.CHECK_VALIDATED,
                          background_check_expires_at=timezone.now() + timedelta(days=1))
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

        response = self.client.post(reverse("login"), {"email": "owner1@example.com", "password": PASSWORD})

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
            name="Session", dojo=dojo, start_time="2020-01-01T10:00:00Z", end_time="2020-01-01T12:00:00Z", places=5,
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
            name="Session", dojo=dojo, start_time="2020-01-01T10:00:00Z", end_time="2020-01-01T12:00:00Z", places=5,
        )
        Registration.objects.create(event=event, ninja=belted, waiting_list=False, position=1)
        award_belt(belted, white, dojo.champion_membership)
        award_belt(belted, yellow, dojo.champion_membership)

        self.client.force_login(guardian)
        response = self.client.get(reverse("account_home"))

        self.assertContains(response, "Yellow belt")
        self.assertNotContains(response, "White belt")


class OrganisationRoleTests(TestCase):
    """OrganisationRole → staff status + a permission group (accounts.organisation):
    the board is read-only (plus the team listing), admins edit the catalogue."""

    def setUp(self):
        self.user = User.objects.create(username="board1", email="b@example.com")

    def _grant(self, role):
        from .models import OrganisationRole

        return OrganisationRole.objects.create(account=self.user, role=role)

    def _fresh(self):
        return User.objects.get(pk=self.user.pk)  # has_perm caches per instance

    def test_board_role_is_read_only_staff(self):
        from .models import OrganisationRole

        self._grant(OrganisationRole.BOARD)
        user = self._fresh()

        self.assertTrue(user.is_staff)
        self.assertTrue(user.has_perm("dojos.view_dojo"))
        self.assertTrue(user.has_perm("events.view_ninjabelt"))
        self.assertTrue(user.has_perm("content.change_organisationteammember"))
        self.assertFalse(user.has_perm("dojos.change_dojo"))
        self.assertFalse(user.has_perm("events.add_ninjabelt"))
        self.assertFalse(user.has_perm("accounts.view_ninja"))
        self.assertFalse(user.has_perm("applications.can_review_background_checks"))
        self.assertFalse(user.has_perm("mailing.view_campaign"))
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
        self.assertTrue(user.has_perm("mailing.add_campaign"))
        self.assertTrue(user.has_perm("mailing.change_segmentrule"))
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

    def test_revoking_keeps_staff_that_is_needed_for_something_else(self):
        from django.contrib.auth.models import Permission

        from .models import OrganisationRole

        self.user.user_permissions.add(Permission.objects.get(codename="can_review_background_checks"))
        self._grant(OrganisationRole.BOARD).delete()
        self.assertTrue(self._fresh().is_staff)

    def test_ninja_accounts_cannot_hold_a_role(self):
        from django.core.exceptions import ValidationError

        from .models import OrganisationRole

        ninja = User.objects.create(username="n1", account_type=User.NINJA)
        with self.assertRaises(ValidationError):
            OrganisationRole(account=ninja, role=OrganisationRole.BOARD).full_clean()

    def test_menu_links_role_holders_to_the_management_dashboards(self):
        from .models import OrganisationRole

        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("account_home")), reverse("admin:index"))
        self._grant(OrganisationRole.BOARD)
        self.assertContains(self.client.get(reverse("account_home")), reverse("admin:index"))

    def test_board_sees_applications_but_cannot_run_the_review_actions(self):
        from .models import OrganisationRole

        self._grant(OrganisationRole.BOARD)
        self.client.force_login(self._fresh())
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
        response = self.client.post(reverse("add_ninja"), {"consent": "on", "name": "Baby", "date_of_birth": _dob(3)})
        self.assertContains(response, "Ninjas are 7 to 17 years old")
        self.assertFalse(Ninja.objects.of_guardian(self.guardian).exists())

    def test_family_sign_up_flags_the_child_row(self):
        self.client.logout()
        response = self.client.post(reverse("register_guardian"), {
            "name": "Jane Doe", "email": "jane@example.com", "phone": "",
            "password": PASSWORD, "password_confirm": PASSWORD,
            "child_1_name": "Old", "child_1_dob": _dob(19), "child_1_notes": "",
        })
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
            username="ellen", email="ellen@example.com", first_name="Ellen", preferred_language="nl-be",
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
        self.assertEqual((account.account_type, account.email, account.first_name), (User.NINJA, "emma@example.com", "Emma"))
        self.assertEqual(account.preferred_language, "nl-be")
        self.assertFalse(account.has_usable_password())
        queued = EmailMessage.objects.get(template_key="ninja_account_created")
        self.assertEqual((queued.user, queued.recipient, queued.status), (account, "emma@example.com", "pending"))

        # The link in the mail sets a password the child can log in with.
        link = next(line.strip() for line in queued.body.splitlines() if "/password-reset/confirm/" in line)
        self.client.logout()
        form = self.client.get(urlsplit(link).path, follow=True)
        self.client.post(form.redirect_chain[-1][0], {"new_password1": PASSWORD, "new_password2": PASSWORD})
        response = self.client.post(reverse("login"), {"email": "emma@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("ninja_detail", kwargs={"ninja_id": self.child.id}))

    def test_email_is_required_and_unique(self):
        self.assertIn("email address is needed", self._create(email="", HTTP_HX_REQUEST="true").context["login_error"])
        self.assertEqual(
            self._create(email="ELLEN@example.com", HTTP_HX_REQUEST="true").context["login_error"],
            "An account already exists with this email.",
        )
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
        add_member(make_dojo("Ghent", champion=make_champion(username="champ")), account, role=DojoMembership.YOUTH_MENTOR)
        self.client.post(self._url("ninja_login_remove"))

        self.client.logout()
        response = self.client.post(reverse("login"), {"email": "emma@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["error"])

    def test_guardian_keeps_editing_a_child_with_a_login(self):
        self._create()
        response = self.client.post(self._url("edit_ninja"), {"name": "Emma P.", "date_of_birth": self.child.date_of_birth})
        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "Emma P.")

    def test_child_sees_and_cancels_its_own_upcoming_session(self):
        self._create()
        self.child.refresh_from_db()
        event = Event.objects.create(
            dojo=make_dojo("Ghent"), name="Scratch", status=Event.OPEN, places=5,
            start_time=timezone.now() + timedelta(days=3), end_time=timezone.now() + timedelta(days=3, hours=2),
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
            name="S", dojo=dojo, status=Event.OPEN, places=5,
            start_time=now + timedelta(days=3), end_time=now + timedelta(days=3, hours=2),
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
        return self.client.post(reverse("edit_ninja", kwargs={"ninja_id": self.child.id}), {
            "name": "Kid", "date_of_birth": self.child.date_of_birth, "home_dojo": home_dojo,
        })

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
        self.assertEqual(set(response.context["home_dojo_choices"]), {self.ghent, self.aalst})

    def test_backfill_picks_the_most_attended_dojo(self):
        from io import StringIO

        from django.core.management import call_command

        past = timezone.now() - timedelta(days=30)
        for n, dojo in enumerate([self.aalst, self.ghent, self.ghent]):
            event = Event.objects.create(name=f"S{n}", dojo=dojo, places=5, start_time=past + timedelta(days=n),
                                         end_time=past + timedelta(days=n, hours=2))
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
        self.client.post(reverse("add_ninja"), {"consent": "on", "name": "Lou", "allergies_notes": "  Gluten-free  "},
                         HTTP_HX_REQUEST="true")
        self.assertEqual(Ninja.objects.get(name="Lou").allergies_notes, "Gluten-free")

    def test_edit_form_shows_and_saves_the_notes(self):
        response = self.client.get(self.edit_url, HTTP_HX_REQUEST="true")
        self.assertContains(response, 'name="allergies_notes"')
        self.assertContains(response, "Peanut allergy")
        self.assertContains(response, "Only the champion")
        response = self.client.post(self.edit_url, {"name": "Emma", "allergies_notes": "Asthma inhaler"},
                                    HTTP_HX_REQUEST="true")
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
