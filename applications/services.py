"""The volunteer onboarding flow (DATA_MODEL.md §10):

1. An adult account applies (Application: mentor or champion).
2. A reviewer requests the account's background check -> the account holder
   gets an email with an upload link (request_background_check).
3. They upload the document (submit_background_check), from that link or
   their account page.
4. A reviewer validates or rejects it (validate_ / reject_background_check).
   Either way the document is deleted at once and a BackgroundCheckHistory
   row records the decision, who made it and when.
5. With a valid check, a reviewer approves the application
   (approve_application): an approved mentor can join dojo teams (and a
   mentor application naming a dojo files a join request there), an
   approved champion can create a dojo.

Renewal is the same loop on the same account: once a validated check
expires, the account loses dojo-team access (never its login) until a new
document is validated.
"""

import uuid

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import ARTICLE_596_2_TEXT, BACKGROUND_CHECK_VALIDITY, Application, BackgroundCheckHistory


class OnboardingError(Exception):
    pass


def _send(user, subject, message):
    if user.email:
        send_mail(subject=subject, message=message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[user.email])


def _greeting(user):
    return f"Hi {user.first_name or user.get_username()},\n\n"


# --- background check -----------------------------------------------------------

def request_background_check(user, request):
    """Ask the account holder for a (new) document. Not limited to first
    requests: re-running it on an account whose check isn't currently valid
    (never done, rejected, or expired) is how a renewal is requested."""
    if user.background_check_valid:
        raise OnboardingError(f"{user} already has a valid background check.")
    if user.background_check_status == User.CHECK_SUBMITTED:
        raise OnboardingError(f"{user} has already uploaded a document that's awaiting review.")
    user.background_check_status = User.CHECK_REQUESTED
    user.background_check_requested_at = timezone.now()
    if user.background_check_token is None:
        user.background_check_token = uuid.uuid4()
    user.save(update_fields=["background_check_status", "background_check_requested_at", "background_check_token"])

    upload_url = request.build_absolute_uri(
        reverse("upload_background_check", kwargs={"token": user.background_check_token})
    )
    _send(user, "Action needed: background check document", (
        _greeting(user)
        + "Thanks for volunteering with CoderDojo — before you can work with a dojo's team, "
        "Belgian law requires a specific extract from the criminal record for anyone in "
        "contact with minors:\n\n"
        f"  {ARTICLE_596_2_TEXT}\n\n"
        "You can request this “uittreksel uit het strafregister, model 2” for free from your "
        "local gemeente/commune, or online via mijndossier.rrn.fgov.be — mention it's for "
        "volunteering with minors (model 2 / Artikel 596.2).\n\n"
        "Once you have it, upload it here (or from your account page when logged in):\n\n"
        f"  {upload_url}\n\n"
        "We'll follow up once it's been reviewed."
    ))


def submit_background_check(user, document):
    if not user.background_check_can_upload:
        raise OnboardingError("There's no background check waiting for a document right now.")
    user.background_check_document = document
    user.background_check_status = User.CHECK_SUBMITTED
    user.background_check_submitted_at = timezone.now()
    user.save(update_fields=["background_check_document", "background_check_status", "background_check_submitted_at"])


def _record_decision(user, reviewer, decision, note=""):
    # The document (a criminal record extract) is only needed for the
    # decision itself: delete it straight away, keep only the outcome.
    if user.background_check_document:
        user.background_check_document.delete(save=False)
    user.background_check_document = None
    BackgroundCheckHistory.objects.create(
        account=user,
        decision=decision,
        reviewed_by=reviewer,
        reviewed_at=user.background_check_reviewed_at,
        requested_at=user.background_check_requested_at,
        submitted_at=user.background_check_submitted_at,
        expires_at=user.background_check_expires_at if decision == BackgroundCheckHistory.VALIDATED else None,
        note=note,
    )


def validate_background_check(user, reviewer, note=""):
    if user.background_check_status != User.CHECK_SUBMITTED:
        raise OnboardingError(f"{user} has no uploaded document awaiting review.")
    now = timezone.now()
    user.background_check_status = User.CHECK_VALIDATED
    user.background_check_reviewed_at = now
    user.background_check_expires_at = now + BACKGROUND_CHECK_VALIDITY
    _record_decision(user, reviewer, BackgroundCheckHistory.VALIDATED, note)
    user.save(update_fields=[
        "background_check_document", "background_check_status",
        "background_check_reviewed_at", "background_check_expires_at",
    ])
    _send(user, "Your background check has been approved", (
        _greeting(user)
        + f"Your background check has been validated. It's valid until "
        f"{timezone.localtime(user.background_check_expires_at):%d/%m/%Y}.\n"
    ))


def reject_background_check(user, reviewer, note=""):
    if user.background_check_status != User.CHECK_SUBMITTED:
        raise OnboardingError(f"{user} has no uploaded document awaiting review.")
    user.background_check_status = User.CHECK_REJECTED
    user.background_check_reviewed_at = timezone.now()
    _record_decision(user, reviewer, BackgroundCheckHistory.REJECTED, note)
    user.save(update_fields=["background_check_document", "background_check_status", "background_check_reviewed_at"])
    _send(user, "Your background check document", (
        _greeting(user)
        + "We couldn't accept the document you uploaded for your background check. You can upload "
        "a new one from your account page; get in touch if you're unsure what's needed.\n"
    ))


# --- applications ----------------------------------------------------------------

def submit_application(account, kind, **fields):
    """One pending (or approved) application per account and kind."""
    if account.is_ninja:
        raise OnboardingError("Only adult accounts can apply.")
    if account.applications.filter(kind=kind, status__in=[Application.PENDING, Application.APPROVED]).exists():
        raise OnboardingError("You've already applied for this — see your account page for its status.")
    application = Application.objects.create(account=account, kind=kind, **fields)
    if kind == Application.MENTOR and application.dojo_id:
        from dojos.team import notify_managers

        notify_managers(
            application.dojo,
            f"{account.team_name} applied to mentor at {application.dojo.name}.",
            url=reverse("dojo_team_manage", kwargs={"dojo_id": application.dojo_id}),
        )
    return application


def approve_application(application, reviewer):
    if application.status != Application.PENDING:
        raise OnboardingError(f"Application {application.pk} has already been decided.")
    if not application.account.background_check_valid:
        raise OnboardingError(f"{application.account} doesn't have a valid background check yet.")
    application.status = Application.APPROVED
    application.decided_by = reviewer
    application.decided_at = timezone.now()
    application.save(update_fields=["status", "decided_by", "decided_at"])

    if application.kind == Application.MENTOR:
        next_step = "You can now ask to join a dojo's team from its page on the site."
        if application.dojo_id:
            from dojos.team import TeamError, request_to_join

            try:
                request_to_join(application.dojo, application.account)
                next_step = (
                    f"We've sent your request to join the {application.dojo.name} team; "
                    "they'll let you know."
                )
            except TeamError:
                pass
    else:
        next_step = "You can now create your dojo from your account page."
    _send(application.account, "Your CoderDojo application has been approved", (
        _greeting(application.account)
        + f"Your application to become a {application.get_kind_display().lower()} has been approved. "
        f"{next_step}\n"
    ))


def reject_application(application, reviewer):
    if application.status != Application.PENDING:
        raise OnboardingError(f"Application {application.pk} has already been decided.")
    application.status = Application.REJECTED
    application.decided_by = reviewer
    application.decided_at = timezone.now()
    application.save(update_fields=["status", "decided_by", "decided_at"])
    _send(application.account, "Your CoderDojo application", (
        _greeting(application.account)
        + "Thank you for applying. Unfortunately we can't approve your application at this time; "
        "get in touch if you'd like to know more.\n"
    ))


# --- who is approved --------------------------------------------------------------

def is_approved(user, kinds):
    return (
        user.is_authenticated
        and not user.is_ninja
        and user.background_check_valid
        and user.applications.filter(kind__in=kinds, status=Application.APPROVED).exists()
    )


def is_approved_mentor(user):
    """May ask to join, or be added to, a dojo's team. An approved champion
    was vetted the same way, so they count too."""
    return is_approved(user, [Application.MENTOR, Application.CHAMPION])


def is_approved_champion(user):
    """May create a dojo (as its champion)."""
    return is_approved(user, [Application.CHAMPION])
