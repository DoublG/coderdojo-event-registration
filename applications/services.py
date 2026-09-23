from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import ARTICLE_596_2_TEXT, BackgroundCheckMixin


def send_background_check_request(application, request):
    """The step after an application sits at status=pending: email the
    applicant explaining the Belgian background-check requirement and a
    link (built from their background_check_token) where they can upload
    it. Works for either DojoApplication or MentorApplication — both
    inherit the token/status/document fields from BackgroundCheckMixin."""
    application.background_check_status = BackgroundCheckMixin.REQUESTED
    application.background_check_requested_at = timezone.now()
    application.save(update_fields=["background_check_status", "background_check_requested_at"])

    upload_url = request.build_absolute_uri(
        reverse("upload_background_check", kwargs={"token": application.background_check_token})
    )
    send_mail(
        subject="Action needed: background check document",
        message=(
            f"Hi {application.applicant_name},\n\n"
            "Thanks for applying — before we can confirm this, Belgian law requires a specific "
            "extract from the criminal record for anyone in contact with minors:\n\n"
            f"  {ARTICLE_596_2_TEXT}\n\n"
            "You can request this “uittreksel uit het strafregister, model 2” for free from "
            "your local gemeente/commune, or online via mijndossier.rrn.fgov.be — mention it's for "
            "volunteering with minors (model 2 / Artikel 596.2).\n\n"
            "Once you have it, upload it here:\n\n"
            f"  {upload_url}\n\n"
            "We'll follow up once it's been reviewed."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[application.applicant_email],
    )


def send_role_activated_email(application, role_label):
    """Sent instead of provision_account's temp-password email when an application's
    applicant_account was already set (applications.admin.approve_and_provision_owner/helper
    promoted an existing, already-logged-in account via accounts.provisioning.attach_role rather
    than creating a new login) — they already have a password, there's nothing to activate, just
    a new role to tell them about."""
    send_mail(
        subject="Your CoderDojo account has a new role",
        message=(
            f"Hi {application.applicant_name},\n\n"
            f"Your application has been approved — your existing CoderDojo account is now also "
            f"a {role_label}. Log in as usual; no new password needed.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[application.applicant_email],
    )
