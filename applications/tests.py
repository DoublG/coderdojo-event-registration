import io

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import BackgroundCheckMixin, DojoApplication, MentorApplication


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
