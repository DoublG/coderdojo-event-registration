import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dojos.models import Dojo, DojoMembership
from dojos.testing import add_member, make_dojo
from events.models import Event, Registration

from .models import DojoOwner, Guardianship, HelperAccount, Participant, User
from .provisioning import attach_role, provision_account, unique_username

PASSWORD = "correct-horse-battery-staple"


def make_ninja(guardian, name, **fields):
    """A ninja linked to `guardian` through a Guardianship."""
    ninja = Participant.objects.create(name=name, **fields)
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


class AddChildViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")

    def test_login_required(self):
        response = self.client.post(reverse("add_ninja"), {"name": "Kid"})
        self.assertEqual(response.status_code, 302)

    def test_post_creates_participant(self):
        self.client.force_login(self.guardian)
        response = self.client.post(
            reverse("add_ninja"),
            {"name": "New Kid", "date_of_birth": "2015-01-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Participant.objects.of_guardian(self.guardian).filter(name="New Kid").exists())

    def test_any_adult_account_can_add_children(self):
        """No separate "guardian" role any more — e.g. a dojo owner adds
        their own child from their account page directly."""
        owner = DojoOwner.objects.create(username="owner1")
        self.client.force_login(owner)
        self.client.post(reverse("add_ninja"), {"name": "Owner Kid"})
        self.assertEqual(list(Participant.objects.of_guardian(owner).values_list("name", flat=True)), ["Owner Kid"])

    def test_ninja_login_cannot_add_children(self):
        ninja_login = User.objects.create(username="kid", account_type=User.NINJA)
        self.client.force_login(ninja_login)
        response = self.client.post(reverse("add_ninja"), {"name": "Nope"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Participant.objects.exists())

    def test_blank_name_creates_nothing(self):
        self.client.force_login(self.guardian)
        self.client.post(reverse("add_ninja"), {"name": "  "})
        self.assertEqual(Participant.objects.of_guardian(self.guardian).count(), 0)


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


class AwardWidgetViewTests(TestCase):
    def test_login_required(self):
        guardian = User.objects.create(username="g1", email="g1@example.com")
        child = make_ninja(guardian, "Kid")
        response = self.client.get(reverse("ninja_awards", kwargs={"ninja_id": child.id}))
        self.assertEqual(response.status_code, 302)

    def test_renders_for_owning_guardian(self):
        guardian = User.objects.create(username="g1", email="g1@example.com")
        child = make_ninja(guardian, "Kid")
        self.client.force_login(guardian)
        response = self.client.get(reverse("ninja_awards", kwargs={"ninja_id": child.id}))
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
        owner = DojoOwner.objects.create(username="owner1", email="owner@example.com")
        mentor = HelperAccount.objects.create(username="mentor1")
        youth = User.objects.create(username="kid", account_type=User.NINJA)
        dojo = make_dojo("Antwerp", champion=owner)
        add_member(dojo, mentor)
        add_member(dojo, youth, DojoMembership.YOUTH_MENTOR)
        event = Event.objects.create(
            name="Antwerp Session", dojo=dojo,
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=1,
        )
        confirmed = Registration.objects.create(event=event, participant=self.child, waiting_list=False, position=1)
        Registration.objects.create(event=event, participant=self.waitlisted_child, waiting_list=True, position=2)
        self.client.force_login(self.guardian)

        with patch("dojos.team.notify") as mock_notify:
            self.client.post(
                reverse("cancel_registration", kwargs={"registration_id": confirmed.id})
            )

        recipient_ids = {call.args[0].pk for call in mock_notify.call_args_list}
        self.assertEqual(recipient_ids, {owner.pk, mentor.pk})
        args, kwargs = mock_notify.call_args
        self.assertIn("Antwerp Session", args[1])
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

        guardian = User.objects.get(email="jane@example.com")
        self.assertRedirects(response, reverse("account_home"))
        self.assertTrue(guardian.check_password(self.valid_password))
        self.assertEqual(guardian.first_name, "Jane")
        self.assertEqual(guardian.last_name, "Doe")
        self.assertEqual(list(Participant.objects.of_guardian(guardian).values_list("name", flat=True)), ["Sam"])
        self.assertEqual(int(self.client.session["_auth_user_id"]), guardian.id)

    def test_valid_post_with_non_contiguous_child_indices_creates_both(self):
        """Simulates a family who added a 2nd/3rd child then removed the
        middle one client-side, leaving gaps in the field numbering."""
        data = self._valid_post_data(
            child_3_name="Alex", child_3_dob="2013-06-15", child_3_level="confident", child_3_notes="Peanut allergy",
        )
        self.client.post(reverse("register_guardian"), data)

        guardian = User.objects.get(email="jane@example.com")
        self.assertEqual(Participant.objects.of_guardian(guardian).count(), 2)
        alex = Participant.objects.of_guardian(guardian).get(name="Alex")
        self.assertEqual(alex.experience_level, "confident")
        self.assertEqual(alex.allergies_notes, "Peanut allergy")

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
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())


class RegisterGuardianWhenLoggedInTests(TestCase):
    """Family sign-up is only for people without an account: a logged-in
    account (any kind) adds its children from its account page instead —
    there's no separate guardian role to attach any more."""

    def test_logged_in_account_is_sent_to_account_page(self):
        owner = DojoOwner.objects.create(username="owner1", email="owner@example.com")
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


class ProvisionAccountTests(TestCase):
    """accounts.provisioning.provision_account — how applications.admin's
    "approve" actions turn an approved DojoApplication/MentorApplication
    into a real DojoOwner/HelperAccount login."""

    LOGIN_URL = "https://coolregistration.example/login"

    def test_creates_account_with_forced_password_change(self):
        account = provision_account(DojoOwner, "Jane Doe", "jane@example.com", self.LOGIN_URL)

        self.assertIsInstance(account, DojoOwner)
        self.assertEqual(account.email, "jane@example.com")
        self.assertEqual(account.first_name, "Jane")
        self.assertEqual(account.last_name, "Doe")
        self.assertTrue(account.must_change_password)
        self.assertTrue(account.has_usable_password())

    def test_works_for_helper_accounts_too(self):
        account = provision_account(HelperAccount, "Tom", "tom@example.com", self.LOGIN_URL)
        self.assertIsInstance(account, HelperAccount)

    def test_emails_the_temporary_password_and_login_link(self):
        provision_account(DojoOwner, "Jane Doe", "jane@example.com", self.LOGIN_URL)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["jane@example.com"])
        self.assertIn(self.LOGIN_URL, message.body)

        account = DojoOwner.objects.get(email="jane@example.com")
        match = re.search(r"Temporary password: (\S+)", message.body)
        self.assertIsNotNone(match)
        self.assertTrue(account.check_password(match.group(1)))

    def test_password_is_random_each_time(self):
        provision_account(DojoOwner, "Jane Doe", "jane1@example.com", self.LOGIN_URL)
        provision_account(DojoOwner, "Jane Doe", "jane2@example.com", self.LOGIN_URL)

        passwords = [
            re.search(r"Temporary password: (\S+)", message.body).group(1) for message in mail.outbox
        ]
        self.assertNotEqual(passwords[0], passwords[1])

    def test_generates_distinct_usernames_for_the_same_name(self):
        first = provision_account(DojoOwner, "Jane Doe", "jane1@example.com", self.LOGIN_URL)
        second = provision_account(DojoOwner, "Jane Doe", "jane2@example.com", self.LOGIN_URL)
        self.assertNotEqual(first.username, second.username)


class AttachRoleTests(TestCase):
    """accounts.provisioning.attach_role — the MTI "promote in place" trick used both by
    applications.admin's approve_and_provision_owner/helper
    when an application's applicant_account is set."""

    def test_adds_role_to_existing_user_without_creating_a_new_one(self):
        owner = DojoOwner.objects.create(username="owner1", email="owner@example.com")
        owner.set_password(PASSWORD)
        owner.save()

        helper = attach_role(owner, HelperAccount)

        self.assertEqual(helper.pk, owner.pk)
        # Base User fields carried over untouched.
        self.assertEqual(helper.email, "owner@example.com")
        self.assertTrue(helper.check_password(PASSWORD))
        # One User row, now resolving as both roles.
        self.assertEqual(DojoOwner.objects.filter(pk=owner.pk).count(), 1)
        self.assertEqual(HelperAccount.objects.filter(pk=owner.pk).count(), 1)
        owner.refresh_from_db()
        self.assertIsNotNone(getattr(owner, "helperaccount", None))

    def test_reattaching_an_existing_role_is_a_safe_no_op(self):
        """The 1-to-n DojoOwner:Dojo case — an already-DojoOwner account approved for a *second*
        dojo application goes through attach_role again for a role it already has."""
        owner = DojoOwner.objects.create(username="owner1", email="owner@example.com")

        result = attach_role(owner, DojoOwner)

        self.assertEqual(result.pk, owner.pk)
        self.assertEqual(DojoOwner.objects.filter(pk=owner.pk).count(), 1)


class BackgroundCheckValidPropertyTests(TestCase):
    def test_valid_when_not_required(self):
        owner = DojoOwner.objects.create(username="owner1", background_check_required=False)
        self.assertTrue(owner.background_check_valid)

    def test_invalid_when_required_and_never_set(self):
        owner = DojoOwner.objects.create(username="owner1", background_check_required=True)
        self.assertFalse(owner.background_check_valid)

    def test_invalid_when_required_and_expired(self):
        owner = DojoOwner.objects.create(
            username="owner1", background_check_required=True,
            background_check_expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(owner.background_check_valid)

    def test_valid_when_required_and_not_yet_expired(self):
        owner = DojoOwner.objects.create(
            username="owner1", background_check_required=True,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertTrue(owner.background_check_valid)


class BackgroundCheckLoginGateTests(TestCase):
    """accounts.views.login refuses a correct password for a DojoOwner/
    HelperAccount whose background check has lapsed — see
    accounts.middleware.BackgroundCheckMiddleware for the same gate on an
    already-open session."""

    def _owner(self, **overrides):
        owner = DojoOwner(username="owner1", email="owner1@example.com", **overrides)
        owner.set_password(PASSWORD)
        owner.save()
        return owner

    def test_blocked_when_required_and_expired(self):
        self._owner(background_check_required=True, background_check_expires_at=timezone.now() - timedelta(days=1))

        response = self.client.post(reverse("login"), {"email": "owner1@example.com", "password": PASSWORD})

        self.assertEqual(response.status_code, 200)
        self.assertIn("background check has expired", response.context["error"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_allowed_when_required_and_valid(self):
        owner = self._owner(
            background_check_required=True, background_check_expires_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(reverse("login"), {"email": "owner1@example.com", "password": PASSWORD})

        self.assertRedirects(response, reverse("account_home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), owner.id)

    def test_allowed_when_not_required(self):
        owner = self._owner(background_check_required=False)

        self.client.post(reverse("login"), {"email": "owner1@example.com", "password": PASSWORD})

        self.assertEqual(int(self.client.session["_auth_user_id"]), owner.id)


class BackgroundCheckMiddlewareTests(TestCase):
    def _owner(self, **overrides):
        owner = DojoOwner(username="owner1", email="owner1@example.com", **overrides)
        owner.set_password(PASSWORD)
        owner.save()
        return owner

    def test_expired_account_redirected_to_renewal_page(self):
        owner = self._owner(background_check_required=True, background_check_expires_at=timezone.now() - timedelta(days=1))
        self.client.force_login(owner)

        response = self.client.get(reverse("home"))

        # fetch_redirect_response=False: this owner has no linked
        # application (see applications.tests.RenewBackgroundCheckViewTests
        # for that page's own behavior), so the target 404s — here we only
        # care that the middleware redirects there at all.
        self.assertRedirects(
            response, reverse("renew_background_check"), fetch_redirect_response=False,
        )

    def test_expired_account_can_still_reach_logout(self):
        owner = self._owner(background_check_required=True, background_check_expires_at=timezone.now() - timedelta(days=1))
        self.client.force_login(owner)

        response = self.client.get(reverse("logout"))

        self.assertRedirects(response, reverse("home"))

    def test_valid_account_is_not_intercepted(self):
        owner = self._owner(
            background_check_required=True, background_check_expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
