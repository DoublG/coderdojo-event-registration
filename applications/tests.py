import io
import re
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.parse import urlparse

from django.contrib.auth.models import Permission
from django.core import mail
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DojoOwner, Guardian, HelperAccount, User
from dojos.models import Dojo, Mentor

from .admin import (
    approve_and_provision_helper,
    approve_and_provision_owner,
    reject_background_check,
    request_background_check,
    validate_background_check,
)
from .models import BackgroundCheckMixin, DojoApplication, MentorApplication


def _request_as(user):
    """A minimal admin-action request: RequestFactory gives us a real
    HttpRequest (so request.build_absolute_uri works for the actions that
    build an email link) without needing a live admin session."""
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


class RegisterDojoViewTests(TestCase):
    def test_get_renders_form(self):
        response = self.client.get(reverse("register_dojo"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["submitted"])

    def test_valid_post_creates_application_and_resets_form(self):
        response = self.client.post(
            reverse("register_dojo"),
            {
                "applicant_name": "Jane Doe",
                "applicant_email": "jane@example.com",
                "area": "Leuven",
                "consent": "on",
                "background_check_consent": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["submitted"])
        self.assertEqual(DojoApplication.objects.count(), 1)
        application = DojoApplication.objects.get()
        self.assertEqual(application.applicant_name, "Jane Doe")
        self.assertEqual(application.status, DojoApplication.PENDING)

    def test_missing_consent_does_not_create_application(self):
        response = self.client.post(
            reverse("register_dojo"),
            {
                "applicant_name": "Jane Doe",
                "applicant_email": "jane@example.com",
                "area": "Leuven",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["submitted"])
        self.assertEqual(DojoApplication.objects.count(), 0)

    def test_authenticated_guardian_gets_prefilled_form(self):
        guardian = Guardian.objects.create(
            username="g1", email="g1@example.com", first_name="Jane", last_name="Doe", phone="0470000000",
        )
        self.client.force_login(guardian)

        response = self.client.get(reverse("register_dojo"))

        initial = response.context["form"].initial
        self.assertEqual(initial["applicant_name"], "Jane Doe")
        self.assertEqual(initial["applicant_email"], "g1@example.com")
        self.assertEqual(initial["applicant_phone"], "0470000000")

    def test_authenticated_submission_links_application_to_account(self):
        guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        self.client.force_login(guardian)

        self.client.post(
            reverse("register_dojo"),
            {
                "applicant_name": "Jane Doe",
                "applicant_email": "g1@example.com",
                "area": "Leuven",
                "consent": "on",
                "background_check_consent": "on",
            },
        )

        application = DojoApplication.objects.get()
        self.assertEqual(application.applicant_account_id, guardian.pk)

    def test_anonymous_submission_leaves_applicant_account_blank(self):
        self.client.post(
            reverse("register_dojo"),
            {
                "applicant_name": "Jane Doe",
                "applicant_email": "jane@example.com",
                "area": "Leuven",
                "consent": "on",
                "background_check_consent": "on",
            },
        )
        self.assertIsNone(DojoApplication.objects.get().applicant_account_id)


class RegisterHelperViewTests(TestCase):
    def test_get_renders_form(self):
        response = self.client.get(reverse("register_helper"))
        self.assertEqual(response.status_code, 200)

    def test_valid_post_creates_application(self):
        response = self.client.post(
            reverse("register_helper"),
            {
                "applicant_name": "Tom",
                "applicant_email": "tom@example.com",
                "role": MentorApplication.VOLUNTEER_MENTOR,
                "background_check_consent": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["submitted"])
        self.assertEqual(MentorApplication.objects.count(), 1)

    def test_authenticated_submission_links_application_to_account(self):
        guardian = Guardian.objects.create(username="g1", email="g1@example.com")
        self.client.force_login(guardian)

        self.client.post(
            reverse("register_helper"),
            {
                "applicant_name": "Guardian One",
                "applicant_email": "g1@example.com",
                "role": MentorApplication.VOLUNTEER_MENTOR,
                "background_check_consent": "on",
            },
        )

        application = MentorApplication.objects.get()
        self.assertEqual(application.applicant_account_id, guardian.pk)

    def test_notifies_the_dojo_owner_when_a_dojo_was_picked(self):
        owner = DojoOwner.objects.create(username="owner1", email="owner@example.com")
        dojo = Dojo.objects.create(name="Ghent", owner=owner)

        with patch("applications.views.notify") as mock_notify:
            self.client.post(
                reverse("register_helper"),
                {
                    "applicant_name": "Priya Nair",
                    "applicant_email": "priya@example.com",
                    "dojo": dojo.id,
                    "role": MentorApplication.VOLUNTEER_MENTOR,
                    "background_check_consent": "on",
                },
            )

        mock_notify.assert_called_once()
        args, kwargs = mock_notify.call_args
        self.assertEqual(args[0], owner)
        self.assertIn("Priya Nair", args[1])
        self.assertIn("Ghent", args[1])
        self.assertEqual(kwargs["dojo"], dojo)

    def test_no_notification_when_no_dojo_was_picked(self):
        with patch("applications.views.notify") as mock_notify:
            self.client.post(
                reverse("register_helper"),
                {
                    "applicant_name": "Tom",
                    "applicant_email": "tom@example.com",
                    "role": MentorApplication.VOLUNTEER_MENTOR,
                    "background_check_consent": "on",
                },
            )
        mock_notify.assert_not_called()

    def test_no_notification_when_the_dojo_has_no_owner(self):
        dojo = Dojo.objects.create(name="Ghent")

        with patch("applications.views.notify") as mock_notify:
            self.client.post(
                reverse("register_helper"),
                {
                    "applicant_name": "Tom",
                    "applicant_email": "tom@example.com",
                    "dojo": dojo.id,
                    "role": MentorApplication.VOLUNTEER_MENTOR,
                    "background_check_consent": "on",
                },
            )
        mock_notify.assert_not_called()


class UploadBackgroundCheckViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.application = DojoApplication.objects.create(
            applicant_name="Jane",
            applicant_email="jane@example.com",
            area="Leuven",
            background_check_status=BackgroundCheckMixin.REQUESTED,
        )

    def test_invalid_token_is_404(self):
        response = self.client.get(
            reverse("upload_background_check", kwargs={"token": "00000000-0000-0000-0000-000000000000"})
        )
        self.assertEqual(response.status_code, 404)

    def test_get_renders_upload_form(self):
        response = self.client.get(
            reverse("upload_background_check", kwargs={"token": self.application.background_check_token})
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["already_submitted"])

    def test_valid_upload_marks_submitted(self):
        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        response = self.client.post(
            reverse("upload_background_check", kwargs={"token": self.application.background_check_token}),
            {"document": document},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["submitted"])
        self.application.refresh_from_db()
        self.assertEqual(self.application.background_check_status, BackgroundCheckMixin.SUBMITTED)
        self.assertTrue(self.application.background_check_document)

        # Clean up the file this test wrote to PRIVATE_MEDIA_ROOT.
        self.application.background_check_document.delete(save=False)

    def test_already_submitted_rejects_further_uploads(self):
        self.application.background_check_status = BackgroundCheckMixin.SUBMITTED
        self.application.save(update_fields=["background_check_status"])

        response = self.client.get(
            reverse("upload_background_check", kwargs={"token": self.application.background_check_token})
        )
        self.assertTrue(response.context["already_submitted"])

    def test_valid_upload_for_mentor_application_marks_submitted(self):
        """_find_application_by_token checks both DojoApplication and
        MentorApplication — cover the second branch too."""
        mentor_application = MentorApplication.objects.create(
            applicant_name="Tom",
            applicant_email="tom@example.com",
            background_check_status=BackgroundCheckMixin.REQUESTED,
        )
        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        response = self.client.post(
            reverse("upload_background_check", kwargs={"token": mentor_application.background_check_token}),
            {"document": document},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["submitted"])
        mentor_application.refresh_from_db()
        self.assertEqual(mentor_application.background_check_status, BackgroundCheckMixin.SUBMITTED)
        self.addCleanup(mentor_application.background_check_document.delete, save=False)


class DownloadBackgroundCheckViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.permission = Permission.objects.get(
            codename="can_review_background_checks",
            content_type__app_label="applications",
        )
        cls.reviewer = User.objects.create(username="reviewer")
        cls.reviewer.user_permissions.add(cls.permission)

    def test_anonymous_is_forbidden(self):
        response = self.client.get(reverse("download_background_check", kwargs={"kind": "dojo", "pk": 1}))
        self.assertEqual(response.status_code, 403)

    def test_authenticated_without_permission_is_forbidden(self):
        plain_user = User.objects.create(username="plain")
        self.client.force_login(plain_user)
        response = self.client.get(reverse("download_background_check", kwargs={"kind": "dojo", "pk": 1}))
        self.assertEqual(response.status_code, 403)

    def test_unknown_kind_is_404_even_for_reviewer(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("download_background_check", kwargs={"kind": "nope", "pk": 1}))
        self.assertEqual(response.status_code, 404)

    def test_reviewer_without_a_document_is_404(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane",
            applicant_email="jane@example.com",
            area="Leuven",
        )
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("download_background_check", kwargs={"kind": "dojo", "pk": application.pk}))
        self.assertEqual(response.status_code, 404)

    def test_reviewer_with_a_document_downloads_it(self):
        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        application = DojoApplication.objects.create(
            applicant_name="Jane",
            applicant_email="jane@example.com",
            area="Leuven",
        )
        application.background_check_document.save("extract.pdf", document, save=True)
        self.addCleanup(application.background_check_document.delete, save=False)

        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("download_background_check", kwargs={"kind": "dojo", "pk": application.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"].startswith("attachment;"), True)

    def test_reviewer_downloads_a_mentor_application_document(self):
        """kind='mentor' takes a different branch of APPLICATION_MODELS_BY_KIND — cover it too."""
        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        application = MentorApplication.objects.create(applicant_name="Tom", applicant_email="tom@example.com")
        application.background_check_document.save("extract.pdf", document, save=True)
        self.addCleanup(application.background_check_document.delete, save=False)

        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("download_background_check", kwargs={"kind": "mentor", "pk": application.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"].startswith("attachment;"), True)


class BackgroundCheckModelTests(TestCase):
    def test_valid_when_validated_and_not_yet_expired(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertTrue(application.has_valid_background_check)

    def test_invalid_once_expired(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(application.has_valid_background_check)

    def test_invalid_when_not_validated(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.SUBMITTED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertFalse(application.has_valid_background_check)


class RequestBackgroundCheckActionTests(TestCase):
    """applications.admin.request_background_check — the admin action that
    starts the flow: email the applicant a link to upload their document."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create(username="staffer", is_staff=True)

    def test_emails_applicant_and_marks_requested(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane", applicant_email="jane@example.com", area="Leuven",
        )
        request_background_check(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.REQUESTED)
        self.assertIsNotNone(application.background_check_requested_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jane@example.com"])
        self.assertIn(str(application.background_check_token), mail.outbox[0].body)

    def test_skips_a_currently_valid_application(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )
        request_background_check(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.VALIDATED)
        self.assertEqual(len(mail.outbox), 0)

    def test_renews_a_validated_but_expired_application(self):
        """VALIDATED but past background_check_expires_at is exactly the
        renewal case — re-requesting must still go out, not be skipped."""
        application = DojoApplication.objects.create(
            applicant_name="Jane", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() - timedelta(days=1),
        )
        request_background_check(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.REQUESTED)
        self.assertEqual(len(mail.outbox), 1)


class ValidateBackgroundCheckActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.permission = Permission.objects.get(
            codename="can_review_background_checks", content_type__app_label="applications",
        )
        cls.reviewer = User.objects.create(username="reviewer")
        cls.reviewer.user_permissions.add(cls.permission)
        cls.plain_staff = User.objects.create(username="staffer", is_staff=True)

    def _application_with_document(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.SUBMITTED,
        )
        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        application.background_check_document.save("extract.pdf", document, save=True)
        return application

    def test_requires_the_review_permission(self):
        application = self._application_with_document()
        self.addCleanup(application.background_check_document.delete, save=False)

        validate_background_check(
            Mock(), _request_as(self.plain_staff), DojoApplication.objects.filter(pk=application.pk),
        )

        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.SUBMITTED)
        self.assertTrue(application.background_check_document)

    def test_validates_and_discards_the_document(self):
        application = self._application_with_document()

        validate_background_check(
            Mock(), _request_as(self.reviewer), DojoApplication.objects.filter(pk=application.pk),
        )

        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.VALIDATED)
        self.assertFalse(application.background_check_document)
        self.assertIsNotNone(application.background_check_reviewed_at)
        self.assertIsNotNone(application.background_check_expires_at)
        self.assertTrue(application.has_valid_background_check)


class RejectBackgroundCheckActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.permission = Permission.objects.get(
            codename="can_review_background_checks", content_type__app_label="applications",
        )
        cls.reviewer = User.objects.create(username="reviewer")
        cls.reviewer.user_permissions.add(cls.permission)
        cls.plain_staff = User.objects.create(username="staffer", is_staff=True)

    def _submitted_application(self):
        return DojoApplication.objects.create(
            applicant_name="Jane", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.SUBMITTED,
        )

    def test_requires_the_review_permission(self):
        application = self._submitted_application()
        reject_background_check(
            Mock(), _request_as(self.plain_staff), DojoApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.SUBMITTED)

    def test_rejects_with_permission(self):
        application = self._submitted_application()
        reject_background_check(
            Mock(), _request_as(self.reviewer), DojoApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.REJECTED)
        self.assertIsNotNone(application.background_check_reviewed_at)


class ApproveAndProvisionOwnerActionTests(TestCase):
    """applications.admin.approve_and_provision_owner — the final step: an
    approved, background-checked DojoApplication becomes a real DojoOwner
    login (see accounts.provisioning.provision_account)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create(username="staffer", is_staff=True)

    def _validated_application(self, **overrides):
        fields = {
            "applicant_name": "Jane Doe",
            "applicant_email": "jane@example.com",
            "area": "Leuven",
            "background_check_status": BackgroundCheckMixin.VALIDATED,
            "background_check_expires_at": timezone.now() + timedelta(days=1),
        }
        fields.update(overrides)
        return DojoApplication.objects.create(**fields)

    def test_blocked_without_a_valid_background_check(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane Doe", applicant_email="jane@example.com", area="Leuven",
        )
        approve_and_provision_owner(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.status, DojoApplication.PENDING)
        self.assertFalse(DojoOwner.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_blocked_once_the_background_check_has_expired(self):
        application = self._validated_application(background_check_expires_at=timezone.now() - timedelta(days=1))
        approve_and_provision_owner(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.status, DojoApplication.PENDING)
        self.assertFalse(DojoOwner.objects.exists())

    def test_provisions_account_and_emails_temp_password(self):
        application = self._validated_application()
        approve_and_provision_owner(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.status, DojoApplication.APPROVED)
        owner = DojoOwner.objects.get(email="jane@example.com")
        self.assertTrue(owner.must_change_password)
        self.assertTrue(owner.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jane@example.com"])

    def test_does_not_reprovision_an_already_approved_application(self):
        application = self._validated_application(status=DojoApplication.APPROVED)
        approve_and_provision_owner(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )
        self.assertFalse(DojoOwner.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_promotes_existing_account_instead_of_provisioning_a_new_one(self):
        """A Guardian applied to start a dojo while already logged in — applicant_account is set,
        so approval should attach the DojoOwner role to that same User row, not mint a second,
        disconnected one with a mailed temp password (see accounts.provisioning.attach_role)."""
        guardian = Guardian.objects.create(username="g1", email="jane@example.com")
        application = self._validated_application(applicant_account=guardian)

        approve_and_provision_owner(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )

        application.refresh_from_db()
        self.assertEqual(application.status, DojoApplication.APPROVED)
        self.assertEqual(User.objects.count(), 2)  # staff_user + guardian — no third row
        owner = DojoOwner.objects.get(pk=guardian.pk)
        self.assertTrue(owner.background_check_required)
        self.assertFalse(owner.must_change_password)
        # Still a Guardian too.
        self.assertTrue(Guardian.objects.filter(pk=guardian.pk).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("Temporary password", mail.outbox[0].body)

    def test_second_dojo_application_from_an_existing_owner_is_a_safe_no_op(self):
        """DojoOwner:Dojo is 1-to-n (dojos.Dojo.owner) — an account that's already a DojoOwner
        can validly apply again for a second dojo."""
        owner = DojoOwner.objects.create(username="owner1", email="owner@example.com")
        application = self._validated_application(applicant_email="owner@example.com", applicant_account=owner)

        approve_and_provision_owner(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )

        self.assertEqual(DojoOwner.objects.filter(pk=owner.pk).count(), 1)


    def test_existing_owner_approved_for_a_second_dojo_application(self):
        """Both applications keep pointing at the same owner — the link is a
        ForeignKey, so the second approval doesn't collide with the first."""
        owner = DojoOwner.objects.create(username="owner1", email="owner@example.com")
        first = self._validated_application(applicant_email="owner@example.com", applicant_account=owner)
        second = self._validated_application(applicant_email="owner@example.com", applicant_account=owner)

        for application in (first, second):
            approve_and_provision_owner(
                Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
            )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.provisioned_owner, owner)
        self.assertEqual(second.provisioned_owner, owner)
        self.assertEqual(set(owner.applications.all()), {first, second})


class ApproveAndProvisionHelperActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create(username="staffer", is_staff=True)

    def test_provisions_helper_account(self):
        application = MentorApplication.objects.create(
            applicant_name="Tom", applicant_email="tom@example.com",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )
        approve_and_provision_helper(
            Mock(), _request_as(self.staff_user), MentorApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.status, MentorApplication.APPROVED)
        self.assertTrue(HelperAccount.objects.filter(email="tom@example.com").exists())

    def test_application_for_a_dojo_links_the_helper_to_it(self):
        """The Mentor link is what gives a helper access to that dojo's
        admin area (dojos.access) — kept off the public team page."""
        dojo = Dojo.objects.create(name="Ghent")
        application = MentorApplication.objects.create(
            applicant_name="Tom", applicant_email="tom@example.com", dojo=dojo,
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )

        approve_and_provision_helper(
            Mock(), _request_as(self.staff_user), MentorApplication.objects.filter(pk=application.pk),
        )

        helper = HelperAccount.objects.get(email="tom@example.com")
        mentor = Mentor.objects.get(helper_account=helper)
        self.assertEqual(mentor.dojo, dojo)
        self.assertEqual(mentor.role, Mentor.VOLUNTEER)
        self.assertFalse(mentor.is_public)

    def test_application_open_to_any_dojo_creates_no_link(self):
        application = MentorApplication.objects.create(
            applicant_name="Tom", applicant_email="tom@example.com",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )

        approve_and_provision_helper(
            Mock(), _request_as(self.staff_user), MentorApplication.objects.filter(pk=application.pk),
        )

        self.assertFalse(Mentor.objects.exists())

    def _validated_helper_application(self, **fields):
        return MentorApplication.objects.create(
            applicant_name="Tom", applicant_email="tom@example.com",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
            **fields,
        )

    def _approve(self, application):
        approve_and_provision_helper(
            Mock(), _request_as(self.staff_user), MentorApplication.objects.filter(pk=application.pk),
        )

    def test_existing_helper_approved_for_a_second_dojo(self):
        """Helpers can help at several dojos, like owners can own several:
        a second approved application adds a second Mentor link (and a
        second provisioned_helper pointer) instead of failing or moving
        the first."""
        ghent = Dojo.objects.create(name="Ghent")
        antwerp = Dojo.objects.create(name="Antwerp")
        first = self._validated_helper_application(dojo=ghent)
        self._approve(first)
        helper = HelperAccount.objects.get(email="tom@example.com")

        second = self._validated_helper_application(dojo=antwerp, applicant_account=helper)
        self._approve(second)

        self.assertEqual(HelperAccount.objects.count(), 1)
        self.assertEqual(
            set(Mentor.objects.filter(helper_account=helper).values_list("dojo__name", flat=True)),
            {"Ghent", "Antwerp"},
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.provisioned_helper, helper)
        self.assertEqual(second.provisioned_helper, helper)
        self.assertEqual(second.status, MentorApplication.APPROVED)

    def test_second_application_for_the_same_dojo_adds_no_duplicate_link(self):
        ghent = Dojo.objects.create(name="Ghent")
        helper = HelperAccount.objects.create(username="tom", email="tom@example.com")
        existing = Mentor.objects.create(name="Tom", dojo=ghent, role=Mentor.VOLUNTEER, helper_account=helper)

        self._approve(self._validated_helper_application(dojo=ghent, applicant_account=helper))

        self.assertEqual(list(Mentor.objects.all()), [existing])

    def test_second_approval_never_shortens_the_accounts_check(self):
        later = timezone.now() + timedelta(days=300)
        helper = HelperAccount.objects.create(
            username="tom", email="tom@example.com",
            background_check_required=True, background_check_expires_at=later,
        )

        self._approve(self._validated_helper_application(dojo=Dojo.objects.create(name="Ghent"), applicant_account=helper))

        helper.refresh_from_db()
        self.assertEqual(helper.background_check_expires_at, later)

    def test_blocked_without_a_valid_background_check(self):
        application = MentorApplication.objects.create(applicant_name="Tom", applicant_email="tom@example.com")
        approve_and_provision_helper(
            Mock(), _request_as(self.staff_user), MentorApplication.objects.filter(pk=application.pk),
        )
        application.refresh_from_db()
        self.assertEqual(application.status, MentorApplication.PENDING)
        self.assertFalse(HelperAccount.objects.exists())

    def test_promotes_existing_account_instead_of_provisioning_a_new_one(self):
        guardian = Guardian.objects.create(username="g1", email="tom@example.com")
        application = MentorApplication.objects.create(
            applicant_name="Tom", applicant_email="tom@example.com", applicant_account=guardian,
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )

        approve_and_provision_helper(
            Mock(), _request_as(self.staff_user), MentorApplication.objects.filter(pk=application.pk),
        )

        self.assertEqual(User.objects.count(), 2)  # staff_user + guardian — no third row
        helper = HelperAccount.objects.get(pk=guardian.pk)
        self.assertTrue(helper.background_check_required)
        self.assertTrue(Guardian.objects.filter(pk=guardian.pk).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("Temporary password", mail.outbox[0].body)


class BackgroundCheckRequestEmailAndUploadFlowTests(TestCase):
    """End-to-end version of the request -> email -> upload journey: unlike
    RequestBackgroundCheckActionTests/UploadBackgroundCheckViewTests (which
    call the admin action function or a known token directly), this drives
    the real admin changelist action URL and then follows the link exactly
    as it appears in the sent email — the same "mail server" Django's test
    runner always swaps in for outgoing mail (django.core.mail.outbox),
    regardless of the project's configured EMAIL_BACKEND."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_superuser(
            username="reviewer-admin", email="reviewer-admin@example.com", password="irrelevant-99",
        )

    def _request_background_check_via_admin(self, application, model_name):
        self.client.force_login(self.staff_user)
        response = self.client.post(
            reverse(f"admin:applications_{model_name}_changelist"),
            {"action": "request_background_check", "_selected_action": [str(application.pk)]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.client.logout()

    def _upload_link_from(self, message):
        match = re.search(r"https?://\S+/applications/background-check/\S+/", message.body)
        self.assertIsNotNone(match, f"No upload link found in email body:\n{message.body}")
        return urlparse(match.group(0)).path

    def test_dojo_application_request_and_upload_via_the_emailed_link(self):
        application = DojoApplication.objects.create(
            applicant_name="Jane Doe", applicant_email="jane@example.com", area="Leuven",
            consent=True, background_check_consent=True,
        )

        self._request_background_check_via_admin(application, "dojoapplication")

        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.REQUESTED)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["jane@example.com"])

        upload_path = self._upload_link_from(message)
        self.assertEqual(
            upload_path,
            reverse("upload_background_check", kwargs={"token": application.background_check_token}),
        )

        get_response = self.client.get(upload_path)
        self.assertEqual(get_response.status_code, 200)
        self.assertFalse(get_response.context["already_submitted"])

        document = io.BytesIO(b"%PDF-1.4 pretend this is a real uittreksel document")
        document.name = "extract.pdf"
        post_response = self.client.post(upload_path, {"document": document})
        self.assertEqual(post_response.status_code, 200)
        self.assertTrue(post_response.context["submitted"])

        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.SUBMITTED)
        self.assertIsNotNone(application.background_check_submitted_at)
        self.assertTrue(application.background_check_document)
        self.addCleanup(application.background_check_document.delete, save=False)

        # Revisiting the same emailed link afterwards must refuse a second upload.
        second_get = self.client.get(upload_path)
        self.assertTrue(second_get.context["already_submitted"])

    def test_mentor_application_request_and_upload_via_the_emailed_link(self):
        application = MentorApplication.objects.create(
            applicant_name="Tom", applicant_email="tom@example.com", background_check_consent=True,
        )

        self._request_background_check_via_admin(application, "mentorapplication")

        self.assertEqual(len(mail.outbox), 1)
        upload_path = self._upload_link_from(mail.outbox[0])

        document = io.BytesIO(b"%PDF-1.4 pretend this is a real uittreksel document")
        document.name = "extract.pdf"
        post_response = self.client.post(upload_path, {"document": document})
        self.assertEqual(post_response.status_code, 200)
        self.assertTrue(post_response.context["submitted"])

        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.SUBMITTED)
        self.addCleanup(application.background_check_document.delete, save=False)

    def test_currently_valid_application_is_not_re_emailed(self):
        """request_background_check skips an application whose check is
        still currently valid — confirm that holds through the real admin
        action too."""
        application = DojoApplication.objects.create(
            applicant_name="Jane Doe", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() + timedelta(days=1),
        )

        self._request_background_check_via_admin(application, "dojoapplication")

        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.VALIDATED)
        self.assertEqual(len(mail.outbox), 0)


class ProvisioningSyncsAccountBackgroundCheckTests(TestCase):
    """approve_and_provision_owner/helper carry the check onto the account
    itself (accounts.User.background_check_required/expires_at) — that's
    what accounts.views.login and BackgroundCheckMiddleware actually gate
    on from here — and link the application back to the account
    (provisioned_owner/provisioned_helper) so a later renewal can sync
    back onto it (see ValidateBackgroundCheckSyncsRenewalToAccountTests)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create(username="staffer", is_staff=True)

    def test_provision_owner_sets_required_and_expiry_on_the_account(self):
        expires_at = timezone.now() + timedelta(days=300)
        application = DojoApplication.objects.create(
            applicant_name="Jane Doe", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.VALIDATED, background_check_expires_at=expires_at,
        )

        approve_and_provision_owner(
            Mock(), _request_as(self.staff_user), DojoApplication.objects.filter(pk=application.pk),
        )

        owner = DojoOwner.objects.get(email="jane@example.com")
        self.assertTrue(owner.background_check_required)
        self.assertEqual(owner.background_check_expires_at, expires_at)
        application.refresh_from_db()
        self.assertEqual(application.provisioned_owner_id, owner.id)

    def test_provision_helper_sets_required_and_expiry_on_the_account(self):
        expires_at = timezone.now() + timedelta(days=300)
        application = MentorApplication.objects.create(
            applicant_name="Tom", applicant_email="tom@example.com",
            background_check_status=BackgroundCheckMixin.VALIDATED, background_check_expires_at=expires_at,
        )

        approve_and_provision_helper(
            Mock(), _request_as(self.staff_user), MentorApplication.objects.filter(pk=application.pk),
        )

        helper = HelperAccount.objects.get(email="tom@example.com")
        self.assertTrue(helper.background_check_required)
        self.assertEqual(helper.background_check_expires_at, expires_at)
        application.refresh_from_db()
        self.assertEqual(application.provisioned_helper_id, helper.id)


class ValidateBackgroundCheckSyncsRenewalToAccountTests(TestCase):
    """Renewal: validating a background check on an application that
    already provisioned an account must push the fresh expiry onto that
    account immediately, not just onto the application row."""

    @classmethod
    def setUpTestData(cls):
        cls.permission = Permission.objects.get(
            codename="can_review_background_checks", content_type__app_label="applications",
        )
        cls.reviewer = User.objects.create(username="reviewer")
        cls.reviewer.user_permissions.add(cls.permission)

    def test_validating_a_renewal_updates_the_linked_owner_account(self):
        owner = DojoOwner.objects.create(
            username="owner1", background_check_required=True,
            background_check_expires_at=timezone.now() - timedelta(days=1),
        )
        application = DojoApplication.objects.create(
            applicant_name="Jane Doe", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.SUBMITTED, provisioned_owner=owner,
        )
        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        application.background_check_document.save("extract.pdf", document, save=True)

        validate_background_check(
            Mock(), _request_as(self.reviewer), DojoApplication.objects.filter(pk=application.pk),
        )

        owner.refresh_from_db()
        application.refresh_from_db()
        self.assertEqual(owner.background_check_expires_at, application.background_check_expires_at)
        self.assertTrue(owner.background_check_valid)

    def test_validating_a_first_time_application_does_not_touch_any_account(self):
        """No provisioned_owner/provisioned_helper yet — nothing to sync to,
        and nothing should error trying."""
        application = DojoApplication.objects.create(
            applicant_name="Jane Doe", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.SUBMITTED,
        )
        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        application.background_check_document.save("extract.pdf", document, save=True)

        validate_background_check(
            Mock(), _request_as(self.reviewer), DojoApplication.objects.filter(pk=application.pk),
        )

        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.VALIDATED)


class RenewBackgroundCheckViewTests(TestCase):
    """applications.views.renew_background_check — where
    accounts.middleware.BackgroundCheckMiddleware sends a logged-in
    DojoOwner/HelperAccount whose check has lapsed, to upload a fresh
    document without needing the emailed token link."""

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("renew_background_check"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_account_with_no_linked_application_is_404(self):
        owner = DojoOwner.objects.create(username="owner1", background_check_required=True)
        self.client.force_login(owner)
        response = self.client.get(reverse("renew_background_check"))
        self.assertEqual(response.status_code, 404)

    def test_owner_can_upload_without_a_token(self):
        owner = DojoOwner.objects.create(
            username="owner1", background_check_required=True,
            background_check_expires_at=timezone.now() - timedelta(days=1),
        )
        application = DojoApplication.objects.create(
            applicant_name="Jane Doe", applicant_email="jane@example.com", area="Leuven",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() - timedelta(days=1),
            provisioned_owner=owner,
        )
        self.client.force_login(owner)

        get_response = self.client.get(reverse("renew_background_check"))
        self.assertEqual(get_response.status_code, 200)
        self.assertFalse(get_response.context["already_submitted"])

        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        post_response = self.client.post(reverse("renew_background_check"), {"document": document})

        self.assertEqual(post_response.status_code, 200)
        self.assertTrue(post_response.context["submitted"])
        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.SUBMITTED)
        self.addCleanup(application.background_check_document.delete, save=False)

    def test_helper_with_several_applications_renews_the_most_recent(self):
        """A helper approved for several dojos has one application each; the
        renewal goes onto the most recently submitted one."""
        helper = HelperAccount.objects.create(
            username="helper1", background_check_required=True,
            background_check_expires_at=timezone.now() - timedelta(days=1),
        )
        common = {
            "applicant_name": "Tom", "applicant_email": "tom@example.com", "provisioned_helper": helper,
            "background_check_status": BackgroundCheckMixin.VALIDATED,
            "background_check_expires_at": timezone.now() - timedelta(days=1),
        }
        older = MentorApplication.objects.create(**common)
        newer = MentorApplication.objects.create(**common)
        MentorApplication.objects.filter(pk=older.pk).update(submitted_at=timezone.now() - timedelta(days=30))
        self.client.force_login(helper)

        response = self.client.get(reverse("renew_background_check"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["application"], newer)

    def test_helper_can_upload_without_a_token(self):
        helper = HelperAccount.objects.create(
            username="helper1", background_check_required=True,
            background_check_expires_at=timezone.now() - timedelta(days=1),
        )
        application = MentorApplication.objects.create(
            applicant_name="Tom", applicant_email="tom@example.com",
            background_check_status=BackgroundCheckMixin.VALIDATED,
            background_check_expires_at=timezone.now() - timedelta(days=1),
            provisioned_helper=helper,
        )
        self.client.force_login(helper)

        document = io.BytesIO(b"pretend this is a pdf")
        document.name = "extract.pdf"
        post_response = self.client.post(reverse("renew_background_check"), {"document": document})

        self.assertEqual(post_response.status_code, 200)
        self.assertTrue(post_response.context["submitted"])
        application.refresh_from_db()
        self.assertEqual(application.background_check_status, BackgroundCheckMixin.SUBMITTED)
        self.addCleanup(application.background_check_document.delete, save=False)
