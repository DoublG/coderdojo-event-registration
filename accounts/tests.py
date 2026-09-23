from django.test import TestCase
from django.urls import reverse

from dojos.models import Dojo
from events.models import Event, Registration

from .models import Guardian, Participant

PASSWORD = "correct-horse-battery-staple"


class LoginViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        cls.guardian.set_password(PASSWORD)
        cls.guardian.save()

    def test_get_renders_form(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_valid_login_by_email_redirects_to_account_page(self):
        response = self.client.post(reverse("login"), {"email": self.guardian.email, "password": PASSWORD})
        self.assertRedirects(response, reverse("guardian_detail", kwargs={"guardian_id": self.guardian.id}))

    def test_valid_login_by_username(self):
        """EmailOrUsernameBackend accepts either — seeded demo accounts are
        keyed by username."""
        response = self.client.post(reverse("login"), {"email": self.guardian.username, "password": PASSWORD})
        self.assertRedirects(response, reverse("guardian_detail", kwargs={"guardian_id": self.guardian.id}))

    def test_invalid_password_shows_error(self):
        response = self.client.post(reverse("login"), {"email": self.guardian.email, "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["error"])

    def test_already_authenticated_redirects_away_from_form(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("login"))
        self.assertRedirects(response, reverse("guardian_detail", kwargs={"guardian_id": self.guardian.id}))


class LogoutViewTests(TestCase):
    def test_logout_redirects_home_and_clears_session(self):
        guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        self.client.force_login(guardian)

        response = self.client.get(reverse("logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ChangePasswordViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = Guardian.objects.create(username="g1", email="g1@example.com", must_change_password=True)
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
        cls.guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        cls.other_guardian = Guardian.objects.create(username="g2", email="g2@example.com")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("guardian_detail", kwargs={"guardian_id": self.guardian.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_own_account_renders(self):
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("guardian_detail", kwargs={"guardian_id": self.guardian.id}))
        self.assertEqual(response.status_code, 200)

    def test_another_guardians_account_is_404(self):
        """404, not 403 — see _get_own_guardian's docstring: a guessed id
        shouldn't even confirm another family's account exists."""
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("guardian_detail", kwargs={"guardian_id": self.other_guardian.id}))
        self.assertEqual(response.status_code, 404)


class AddChildViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = Guardian.objects.create(username="g1", email="g1@example.com")

    def test_login_required(self):
        response = self.client.post(reverse("add_child", kwargs={"guardian_id": self.guardian.id}), {"name": "Kid"})
        self.assertEqual(response.status_code, 302)

    def test_post_creates_participant(self):
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse("add_child", kwargs={"guardian_id": self.guardian.id}),
            {"name": "New Kid", "date_of_birth": "2015-01-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.guardian.children.filter(name="New Kid").exists())

    def test_blank_name_creates_nothing(self):
        self.client.force_login(self.guardian)
        self.client.post(reverse("add_child", kwargs={"guardian_id": self.guardian.id}), {"name": "  "})
        self.assertEqual(self.guardian.children.count(), 0)


class ChildDetailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        cls.other_guardian = Guardian.objects.create(username="g2", email="g2@example.com")
        cls.child = Participant.objects.create(guardian=cls.guardian, name="Kid One")
        cls.other_child = Participant.objects.create(guardian=cls.other_guardian, name="Kid Two")

    def test_own_child_renders(self):
        self.client.force_login(self.guardian)
        response = self.client.get(
            reverse("child_detail", kwargs={"guardian_id": self.guardian.id, "child_id": self.child.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_another_familys_child_is_404(self):
        self.client.force_login(self.guardian)
        response = self.client.get(
            reverse("child_detail", kwargs={"guardian_id": self.guardian.id, "child_id": self.other_child.id})
        )
        self.assertEqual(response.status_code, 404)


class EditChildViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        cls.child = Participant.objects.create(guardian=cls.guardian, name="Kid One")

    def test_get_returns_edit_form_partial(self):
        self.client.force_login(self.guardian)
        response = self.client.get(
            reverse("edit_child", kwargs={"guardian_id": self.guardian.id, "child_id": self.child.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/partials/_child_header_edit.html")

    def test_post_updates_name(self):
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse("edit_child", kwargs={"guardian_id": self.guardian.id, "child_id": self.child.id}),
            {"name": "Renamed Kid", "date_of_birth": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/partials/_child_header_display.html")
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "Renamed Kid")


class AwardWidgetViewTests(TestCase):
    def test_login_required(self):
        guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        child = Participant.objects.create(guardian=guardian, name="Kid")
        response = self.client.get(reverse("award_widget", kwargs={"guardian_id": guardian.id, "child_id": child.id}))
        self.assertEqual(response.status_code, 302)

    def test_renders_for_owning_guardian(self):
        guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        child = Participant.objects.create(guardian=guardian, name="Kid")
        self.client.force_login(guardian)
        response = self.client.get(reverse("award_widget", kwargs={"guardian_id": guardian.id, "child_id": child.id}))
        self.assertEqual(response.status_code, 200)


class CancelRegistrationViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        cls.child = Participant.objects.create(guardian=cls.guardian, name="Kid One")
        cls.waitlisted_child = Participant.objects.create(guardian=cls.guardian, name="Kid Two")
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
            participant=cls.child,
            waiting_list=False,
            position=1,
        )
        cls.waitlisted = Registration.objects.create(
            event=cls.event,
            participant=cls.waitlisted_child,
            waiting_list=True,
            position=2,
        )

    def test_cancelling_a_confirmed_spot_promotes_next_in_line(self):
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse(
                "cancel_registration", kwargs={"guardian_id": self.guardian.id, "registration_id": self.confirmed.id}
            )
        )
        self.assertRedirects(response, reverse("guardian_detail", kwargs={"guardian_id": self.guardian.id}))
        self.assertFalse(Registration.objects.filter(id=self.confirmed.id).exists())
        self.waitlisted.refresh_from_db()
        self.assertFalse(self.waitlisted.waiting_list)

    def test_cannot_cancel_another_familys_registration(self):
        other_guardian = Guardian.objects.create(username="g2", email="g2@example.com")
        self.client.force_login(other_guardian)
        response = self.client.post(
            reverse(
                "cancel_registration", kwargs={"guardian_id": other_guardian.id, "registration_id": self.confirmed.id}
            )
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Registration.objects.filter(id=self.confirmed.id).exists())


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
            "child_1_dob": "2015-01-01",
            "child_1_level": "new",
            "child_1_notes": "",
        }
        data.update(overrides)
        return data

    def test_get_renders_one_empty_child_row(self):
        response = self.client.get(reverse("register_guardian"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["child_rows"]), 1)

    def test_valid_post_creates_account_logs_in_and_redirects(self):
        response = self.client.post(reverse("register_guardian"), self._valid_post_data())

        guardian = Guardian.objects.get(email="jane@example.com")
        self.assertRedirects(response, reverse("guardian_detail", kwargs={"guardian_id": guardian.id}))
        self.assertTrue(guardian.check_password(self.valid_password))
        self.assertEqual(guardian.first_name, "Jane")
        self.assertEqual(guardian.last_name, "Doe")
        self.assertEqual(list(guardian.children.values_list("name", flat=True)), ["Sam"])
        self.assertEqual(int(self.client.session["_auth_user_id"]), guardian.id)

    def test_valid_post_with_non_contiguous_child_indices_creates_both(self):
        """Simulates a family who added a 2nd/3rd child then removed the
        middle one client-side, leaving gaps in the field numbering."""
        data = self._valid_post_data(
            child_3_name="Alex", child_3_dob="2013-06-15", child_3_level="confident", child_3_notes="Peanut allergy",
        )
        self.client.post(reverse("register_guardian"), data)

        guardian = Guardian.objects.get(email="jane@example.com")
        self.assertEqual(guardian.children.count(), 2)
        alex = guardian.children.get(name="Alex")
        self.assertEqual(alex.experience_level, "confident")
        self.assertEqual(alex.allergies_notes, "Peanut allergy")

    def test_duplicate_email_is_rejected(self):
        Guardian.objects.create(username="existing", email="jane@example.com")

        response = self.client.post(reverse("register_guardian"), self._valid_post_data())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("email"))
        self.assertEqual(Guardian.objects.filter(email="jane@example.com").count(), 1)

    def test_weak_password_is_rejected(self):
        response = self.client.post(reverse("register_guardian"), self._valid_post_data(password="password"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("password"))
        self.assertFalse(Guardian.objects.filter(email="jane@example.com").exists())

    def test_missing_consent_is_rejected(self):
        response = self.client.post(reverse("register_guardian"), self._valid_post_data(consent=""))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("consent"))
        self.assertFalse(Guardian.objects.filter(email="jane@example.com").exists())

    def test_child_missing_required_fields_is_rejected(self):
        response = self.client.post(
            reverse("register_guardian"), self._valid_post_data(child_1_name="", child_1_dob="")
        )

        self.assertEqual(response.status_code, 200)
        row = response.context["child_rows"][0]
        self.assertIn("name", row["errors"])
        self.assertIn("dob", row["errors"])
        self.assertFalse(Guardian.objects.filter(email="jane@example.com").exists())
        self.assertFalse(Participant.objects.exists())

    def test_no_children_is_rejected(self):
        data = self._valid_post_data()
        del data["child_1_name"]
        del data["child_1_dob"]
        del data["child_1_level"]
        del data["child_1_notes"]

        response = self.client.post(reverse("register_guardian"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["children_error"])
        self.assertFalse(Guardian.objects.filter(email="jane@example.com").exists())
