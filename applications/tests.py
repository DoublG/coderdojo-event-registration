import io
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from dojos.models import Dojo, DojoMembership
from dojos.testing import make_champion, make_dojo, make_mentor
from mailing.models import EmailMessage

from . import services
from .admin import (
    ApplicationAdmin,
    BackgroundCheckAdmin,
    approve_applications,
    reject_checks,
    request_check_for_applicants,
    validate_checks,
)
from .models import Application, BackgroundCheck, BackgroundCheckHistory


def _request_as(user):
    """A minimal admin-action request: a real HttpRequest (so
    build_absolute_uri works for the emailed link) without a live admin
    session. message_user is mocked on the ModelAdmin side."""
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def _document():
    document = io.BytesIO(b"pretend this is a pdf")
    document.name = "extract.pdf"
    return document


def _uploaded():
    return SimpleUploadedFile("extract.pdf", b"pretend this is a pdf", content_type="application/pdf")


def _submitted_account(username="applicant", **fields):
    """An account whose uploaded document is awaiting review."""
    user = User.objects.create(username=username, email=f"{username}@example.com", **fields)
    user.background_check_status = User.CHECK_REQUESTED
    user.save(update_fields=["background_check_status"])
    services.submit_background_check(user, _uploaded())
    return user


class _CleanupDocumentsMixin:
    """Documents written to private storage by a test are removed afterwards
    (a decision deletes them anyway; this covers tests that stop earlier)."""

    def tearDown(self):
        for user in User.objects.exclude(background_check_document="").exclude(background_check_document=None):
            user.background_check_document.delete(save=False)
        super().tearDown()


# --- applying ------------------------------------------------------------------------

class ApplyViewTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create(username="jane", first_name="Jane", email="jane@example.com")

    def test_login_required(self):
        for name in ("register_dojo", "register_helper"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_ninja_login_cannot_apply(self):
        kid = User.objects.create(username="kid", account_type=User.NINJA)
        self.client.force_login(kid)
        self.assertEqual(self.client.get(reverse("register_helper")).status_code, 404)

    def test_champion_application_is_saved_on_the_account(self):
        self.client.force_login(self.parent)

        response = self.client.post(reverse("register_dojo"), {
            "phone": "0470000000", "area": "Leuven", "preferred_schedule": "Saturdays",
            "proposed_venue": "", "message": "Let's do this", "consent": "on", "background_check_consent": "on",
        })

        self.assertTrue(response.context["submitted"])
        application = Application.objects.get()
        self.assertEqual((application.account, application.kind, application.status),
                         (self.parent, Application.CHAMPION, Application.PENDING))
        self.assertEqual(application.area, "Leuven")
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.phone, "0470000000")

    def test_consents_are_required(self):
        self.client.force_login(self.parent)
        response = self.client.post(reverse("register_dojo"), {"area": "Leuven"})
        self.assertFalse(response.context["submitted"])
        self.assertTrue(response.context["form"].errors.get("consent"))
        self.assertFalse(Application.objects.exists())

    def test_one_pending_application_per_kind(self):
        Application.objects.create(account=self.parent, kind=Application.MENTOR)
        self.client.force_login(self.parent)
        response = self.client.get(reverse("register_helper"))
        self.assertIsNotNone(response.context["error"])
        # Applying as a champion is a separate kind, still allowed.
        self.assertIsNone(self.client.get(reverse("register_dojo")).context["error"])

    def test_mentor_application_for_a_dojo_notifies_its_team(self):
        champion = make_champion(username="owner1")
        dojo = make_dojo("Ghent", champion=champion)
        self.client.force_login(self.parent)

        with patch("dojos.team.notify") as mock_notify:
            self.client.post(reverse("register_helper"), {
                "dojo": dojo.id, "mentor_role": Application.VOLUNTEER_MENTOR,
                "message": "", "background_check_consent": "on",
            })

        self.assertEqual({c.args[0].pk for c in mock_notify.call_args_list}, {champion.pk})
        self.assertEqual(Application.objects.get(account=self.parent).dojo, dojo)

    def test_dojo_choices_are_public_dojos_only(self):
        live = make_dojo("Live")
        make_dojo("Draft", status=Dojo.DRAFT)
        self.client.force_login(self.parent)
        response = self.client.get(reverse("register_helper"))
        self.assertEqual(list(response.context["form"].fields["dojo"].queryset), [live])


# --- the background check -------------------------------------------------------------

class BackgroundCheckFlowTests(_CleanupDocumentsMixin, TestCase):
    def setUp(self):
        call_command("load_mail_templates", stdout=io.StringIO())
        self.reviewer = User.objects.create(username="reviewer", is_staff=True)
        self.user = User.objects.create(username="tom", first_name="Tom", email="tom@example.com")

    def test_request_sets_status_token_and_emails_the_link(self):
        services.request_background_check(self.user, _request_as(self.reviewer))

        self.user.refresh_from_db()
        self.assertEqual(self.user.background_check_status, User.CHECK_REQUESTED)
        self.assertIsNotNone(self.user.background_check_token)
        queued = EmailMessage.objects.get(template_key="background_check_requested")
        self.assertEqual((queued.recipient, queued.category, queued.status), ("tom@example.com", "service", "pending"))
        self.assertIn(reverse("upload_background_check", kwargs={"token": self.user.background_check_token}),
                      queued.body)

    def test_request_refused_while_valid_or_awaiting_review(self):
        valid = make_mentor(username="valid")
        with self.assertRaises(services.OnboardingError):
            services.request_background_check(valid, _request_as(self.reviewer))
        waiting = _submitted_account("waiting")
        with self.assertRaises(services.OnboardingError):
            services.request_background_check(waiting, _request_as(self.reviewer))

    def test_upload_via_emailed_link_without_logging_in(self):
        services.request_background_check(self.user, _request_as(self.reviewer))
        self.user.refresh_from_db()
        url = reverse("upload_background_check", kwargs={"token": self.user.background_check_token})

        response = self.client.post(url, {"document": _document()})

        self.assertTrue(response.context["submitted"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.background_check_status, User.CHECK_SUBMITTED)
        self.assertTrue(self.user.background_check_document)

    def test_unknown_token_is_404(self):
        url = reverse("upload_background_check", kwargs={"token": "00000000-0000-0000-0000-000000000000"})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_no_upload_when_nothing_was_requested(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("renew_background_check"), {"document": _document()})
        self.assertTrue(response.context["already_submitted"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.background_check_status, User.CHECK_NOT_REQUESTED)

    def test_validate_deletes_document_sets_expiry_and_writes_history(self):
        user = _submitted_account()
        storage, path = user.background_check_document.storage, user.background_check_document.name

        services.validate_background_check(user, self.reviewer, note="All good")

        user.refresh_from_db()
        self.assertEqual(user.background_check_status, User.CHECK_VALIDATED)
        self.assertTrue(user.background_check_valid)
        self.assertFalse(user.background_check_document)
        self.assertFalse(storage.exists(path))
        history = BackgroundCheckHistory.objects.get(account=user)
        self.assertEqual((history.decision, history.reviewed_by, history.note),
                         (BackgroundCheckHistory.VALIDATED, self.reviewer, "All good"))
        self.assertEqual(history.expires_at, user.background_check_expires_at)

    def test_reject_deletes_document_writes_history_and_allows_a_new_upload(self):
        user = _submitted_account()
        storage, path = user.background_check_document.storage, user.background_check_document.name

        services.reject_background_check(user, self.reviewer)

        user.refresh_from_db()
        self.assertEqual(user.background_check_status, User.CHECK_REJECTED)
        self.assertFalse(user.background_check_document)
        self.assertFalse(storage.exists(path))
        self.assertTrue(user.background_check_can_upload)
        self.assertEqual(BackgroundCheckHistory.objects.get(account=user).decision, BackgroundCheckHistory.REJECTED)

    def test_history_is_append_only_across_renewals(self):
        user = _submitted_account()
        services.reject_background_check(user, self.reviewer)
        services.submit_background_check(user, _uploaded())
        services.validate_background_check(user, self.reviewer)
        self.assertEqual(
            list(user.background_check_history.order_by("reviewed_at").values_list("decision", flat=True)),
            [BackgroundCheckHistory.REJECTED, BackgroundCheckHistory.VALIDATED],
        )

    def test_expired_check_can_be_renewed_from_the_account(self):
        user = make_mentor(username="m1")
        user.background_check_expires_at = timezone.now() - timedelta(days=1)
        user.save(update_fields=["background_check_expires_at"])
        self.client.force_login(user)

        response = self.client.post(reverse("renew_background_check"), {"document": _document()})

        self.assertTrue(response.context["submitted"])
        user.refresh_from_db()
        self.assertEqual(user.background_check_status, User.CHECK_SUBMITTED)


# --- approving -------------------------------------------------------------------------

class ApprovalTests(TestCase):
    def setUp(self):
        call_command("load_mail_templates", stdout=io.StringIO())
        self.reviewer = User.objects.create(username="reviewer", is_staff=True)
        self.applicant = User.objects.create(username="tom", email="tom@example.com")

    def _validate(self, user):
        user.background_check_status = User.CHECK_VALIDATED
        user.background_check_expires_at = timezone.now() + timedelta(days=365)
        user.save(update_fields=["background_check_status", "background_check_expires_at"])

    def test_approval_needs_a_valid_check(self):
        application = Application.objects.create(account=self.applicant, kind=Application.MENTOR)
        with self.assertRaises(services.OnboardingError):
            services.approve_application(application, self.reviewer)
        application.refresh_from_db()
        self.assertEqual(application.status, Application.PENDING)

    def test_approved_mentor_can_join_teams(self):
        self._validate(self.applicant)
        application = Application.objects.create(account=self.applicant, kind=Application.MENTOR)
        self.assertFalse(services.is_approved_mentor(self.applicant))

        services.approve_application(application, self.reviewer)

        application.refresh_from_db()
        self.assertEqual((application.status, application.decided_by), (Application.APPROVED, self.reviewer))
        self.assertTrue(services.is_approved_mentor(self.applicant))
        self.assertFalse(services.is_approved_champion(self.applicant))
        self.assertIn("approved", EmailMessage.objects.get(template_key="application_approved").subject)

    def test_decision_mails_are_queued_in_the_applicants_language(self):
        self._validate(self.applicant)
        User.objects.filter(pk=self.applicant.pk).update(preferred_language="fr-be")
        self.applicant.refresh_from_db()
        champion = Application.objects.create(account=self.applicant, kind=Application.CHAMPION)
        services.approve_application(champion, self.reviewer)
        queued = EmailMessage.objects.get(template_key="application_approved")
        self.assertEqual((queued.language, queued.category), ("fr-be", "service"))
        self.assertIn("créer votre dojo", queued.body)

    def test_a_missing_template_never_blocks_a_decision(self):
        from mailing.models import EmailTemplate

        EmailTemplate.objects.all().delete()
        self._validate(self.applicant)
        application = Application.objects.create(account=self.applicant, kind=Application.MENTOR)
        with self.assertLogs("mailing.services", level="ERROR"):
            services.approve_application(application, self.reviewer)
        application.refresh_from_db()
        self.assertEqual(application.status, Application.APPROVED)

    def test_mentor_approval_for_a_dojo_files_a_join_request(self):
        self._validate(self.applicant)
        dojo = make_dojo("Ghent", champion=make_champion(username="owner1"))
        application = Application.objects.create(account=self.applicant, kind=Application.MENTOR, dojo=dojo)

        services.approve_application(application, self.reviewer)

        membership = DojoMembership.objects.get(dojo=dojo, user=self.applicant)
        self.assertEqual((membership.role, membership.status), (DojoMembership.MENTOR, DojoMembership.REQUESTED))

    def test_approved_champion_counts_as_approved_mentor_too(self):
        self._validate(self.applicant)
        application = Application.objects.create(account=self.applicant, kind=Application.CHAMPION)
        services.approve_application(application, self.reviewer)
        self.assertTrue(services.is_approved_champion(self.applicant))
        self.assertTrue(services.is_approved_mentor(self.applicant))

    def test_approval_lapses_with_the_check(self):
        champion = make_champion(username="c1")
        champion.background_check_expires_at = timezone.now() - timedelta(days=1)
        champion.save(update_fields=["background_check_expires_at"])
        self.assertFalse(services.is_approved_champion(champion))

    def test_reject_application(self):
        application = Application.objects.create(account=self.applicant, kind=Application.CHAMPION)
        services.reject_application(application, self.reviewer)
        application.refresh_from_db()
        self.assertEqual(application.status, Application.REJECTED)
        # A rejected application doesn't block applying again.
        self.client.force_login(self.applicant)
        self.assertIsNone(self.client.get(reverse("register_dojo")).context["error"])


# --- admin actions -----------------------------------------------------------------------

class AdminActionTests(_CleanupDocumentsMixin, TestCase):
    def setUp(self):
        self.staff = User.objects.create(username="staff", is_staff=True)
        reviewer = User.objects.create(username="reviewer", is_staff=True)
        reviewer.user_permissions.add(Permission.objects.get(codename="can_review_background_checks"))
        self.reviewer = User.objects.get(pk=reviewer.pk)  # fresh permission cache
        self.application_admin = ApplicationAdmin(Application, AdminSite())
        self.check_admin = BackgroundCheckAdmin(BackgroundCheck, AdminSite())
        self.application_admin.message_user = Mock()
        self.check_admin.message_user = Mock()

    def test_request_check_for_applicants(self):
        applicant = User.objects.create(username="a1", email="a1@example.com")
        Application.objects.create(account=applicant, kind=Application.MENTOR)

        request_check_for_applicants(self.application_admin, _request_as(self.staff), Application.objects.all())

        applicant.refresh_from_db()
        self.assertEqual(applicant.background_check_status, User.CHECK_REQUESTED)

    def test_validate_needs_the_reviewer_permission(self):
        user = _submitted_account()
        validate_checks(self.check_admin, _request_as(self.staff), BackgroundCheck.objects.filter(pk=user.pk))
        user.refresh_from_db()
        self.assertEqual(user.background_check_status, User.CHECK_SUBMITTED)

        validate_checks(self.check_admin, _request_as(self.reviewer), BackgroundCheck.objects.filter(pk=user.pk))
        user.refresh_from_db()
        self.assertEqual(user.background_check_status, User.CHECK_VALIDATED)
        self.assertEqual(user.background_check_history.get().reviewed_by, self.reviewer)

    def test_reject_needs_the_reviewer_permission(self):
        user = _submitted_account()
        reject_checks(self.check_admin, _request_as(self.staff), BackgroundCheck.objects.filter(pk=user.pk))
        user.refresh_from_db()
        self.assertEqual(user.background_check_status, User.CHECK_SUBMITTED)

    def test_approve_action_skips_applicants_without_a_valid_check(self):
        ready = make_mentor(username="ready")
        Application.objects.filter(account=ready).delete()
        pending_ready = Application.objects.create(account=ready, kind=Application.MENTOR)
        not_ready = Application.objects.create(account=User.objects.create(username="nr"), kind=Application.MENTOR)

        approve_applications(self.application_admin, _request_as(self.staff), Application.objects.all())

        pending_ready.refresh_from_db()
        not_ready.refresh_from_db()
        self.assertEqual(pending_ready.status, Application.APPROVED)
        self.assertEqual(not_ready.status, Application.PENDING)

    def test_background_check_list_hides_accounts_without_a_check(self):
        User.objects.create(username="parent")
        in_progress = _submitted_account()
        queryset = self.check_admin.get_queryset(_request_as(self.reviewer))
        self.assertEqual([u.pk for u in queryset], [in_progress.pk])


class DownloadBackgroundCheckTests(_CleanupDocumentsMixin, TestCase):
    def setUp(self):
        self.user = _submitted_account()
        self.url = reverse("download_background_check", kwargs={"user_id": self.user.pk})

    def test_requires_the_reviewer_permission(self):
        self.client.force_login(User.objects.create(username="staff", is_staff=True))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_a_download_is_recorded_in_the_audit_log(self):
        from auditlog.models import LogEntry

        reviewer = User.objects.create(username="reviewer")
        reviewer.user_permissions.add(Permission.objects.get(codename="can_review_background_checks"))
        self.client.force_login(reviewer)
        self.client.get(self.url)
        entry = LogEntry.objects.get_for_object(self.user).get(action=LogEntry.Action.ACCESS)
        self.assertEqual(entry.actor, reviewer)

    def test_reviewer_downloads_the_document_until_it_is_decided(self):
        reviewer = User.objects.create(username="reviewer")
        reviewer.user_permissions.add(Permission.objects.get(codename="can_review_background_checks"))
        self.client.force_login(reviewer)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"pretend this is a pdf")

        self.user.refresh_from_db()
        services.validate_background_check(self.user, reviewer)
        self.assertEqual(self.client.get(self.url).status_code, 404)


# --- creating a dojo -----------------------------------------------------------------------

@patch("dojos.views.geocode", return_value=(51.05, 3.72))
@patch("dojos.views.find_province", return_value=None)
class DojoCreateTests(TestCase):
    def test_approved_champion_creates_a_draft_dojo_they_run(self, _province, _geocode):
        champion = make_champion(username="c1")
        self.client.force_login(champion)

        response = self.client.post(reverse("dojo_create"), {
            "name": "CoderDojo Leuven", "address": "Ladeuzeplein 21, Leuven", "email": "hi@leuven.example",
        })

        dojo = Dojo.objects.get(name="CoderDojo Leuven")
        self.assertRedirects(response, reverse("dojo_manage", kwargs={"dojo_id": dojo.id}))
        self.assertEqual((dojo.status, dojo.created_by), (Dojo.DRAFT, champion))
        self.assertIsNotNone(dojo.location)
        self.assertEqual(dojo.champion.pk, champion.pk)
        # A draft is hidden from the public site, but its champion can manage it.
        self.assertEqual(self.client.get(reverse("dojo_detail", kwargs={"dojo_id": dojo.id})).status_code, 404)
        self.assertEqual(self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id})).status_code, 200)

    def test_not_approved_as_champion_is_turned_away(self, _province, _geocode):
        for user in (User.objects.create(username="parent"), make_mentor(username="m1")):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.post(reverse("dojo_create"), {"name": "Nope"})
                self.assertRedirects(response, reverse("account_home"))
        self.assertFalse(Dojo.objects.filter(name="Nope").exists())
