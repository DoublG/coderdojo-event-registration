import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .storage import private_storage

# How long a validated background check stays valid before it must be
# redone — the criminal record extract is a snapshot at issue time, not a
# standing clearance.
BACKGROUND_CHECK_VALIDITY = timedelta(days=365)

# The Belgian legal citation this whole flow exists for — quoted verbatim
# (in Dutch, as the actual legal text) rather than paraphrased, since it's
# what applicants need to ask their gemeente/mijndossier.rrn.fgov.be for.
ARTICLE_596_2_TEXT = (
    "Artikel 596.2 (‘minderjarigenmodel’) is nodig voor specifieke activiteiten met "
    "contacten met kinderen en jongeren, zoals opvoeding, psycho-medisch-sociale begeleiding, "
    "hulpverlening aan de jeugd, kinderbescherming, animatie of begeleiding van minderjarigen."
)


class BackgroundCheckMixin(models.Model):
    """Belgian law requires a specific extract from the criminal record
    (uittreksel model 2, Artikel 596.2 — see ARTICLE_596_2_TEXT) for anyone
    who'll be in contact with minors, so both DojoApplication (a dojo's
    lead coach) and MentorApplication (any volunteer) go through this
    after their initial submission: an admin requests it (which emails the
    applicant a link built from background_check_token), they upload it at
    that link, and an admin reviews the upload before the account gets
    provisioned — see applications.admin and applications.services.
    Mandatory for every applicant here — both roles are adults; anyone
    younger is a ninja (accounts.Participant) who'd be promoted to a
    mentor role through a separate flow, not this one.

    This same request/upload/review flow is also how a background check
    gets *renewed*: DojoApplication/MentorApplication double as the
    permanent background-check record for the account it provisioned
    (see provisioned_owner/provisioned_helper), not just a one-time
    application, so admins re-run "Request background check document" on
    the same row as it nears/passes expiry. See accounts.User.background_check_valid
    and accounts.middleware.BackgroundCheckMiddleware for how a lapsed
    check disables that account's login."""

    NOT_REQUESTED = "not_requested"
    REQUESTED = "requested"
    SUBMITTED = "submitted"
    VALIDATED = "validated"
    REJECTED = "rejected"
    BACKGROUND_CHECK_STATUS_CHOICES = [
        (NOT_REQUESTED, "Not requested yet"),
        (REQUESTED, "Requested — waiting on applicant"),
        (SUBMITTED, "Submitted — awaiting review"),
        (VALIDATED, "Validated"),
        (REJECTED, "Rejected"),
    ]

    background_check_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    background_check_status = models.CharField(
        max_length=20, choices=BACKGROUND_CHECK_STATUS_CHOICES, default=NOT_REQUESTED,
    )
    background_check_document = models.FileField(
        upload_to="background_checks/", storage=private_storage, null=True, blank=True,
        help_text="The applicant's uittreksel uit het strafregister, model 2 (Artikel 596.2). "
                  "Only readable by an approved reviewer (applications.can_review_background_checks) "
                  "via the protected download view — never a public media URL. The file itself is "
                  "deleted once validated; only the decision and its expiry date are kept.",
    )
    background_check_requested_at = models.DateTimeField(null=True, blank=True)
    background_check_submitted_at = models.DateTimeField(null=True, blank=True)
    background_check_reviewed_at = models.DateTimeField(null=True, blank=True)
    background_check_expires_at = models.DateTimeField(
        null=True, blank=True, help_text="Set on validation; the check must be redone after this date.",
    )

    class Meta:
        abstract = True

    @property
    def has_valid_background_check(self):
        return (
            self.background_check_status == self.VALIDATED
            and self.background_check_expires_at is not None
            and self.background_check_expires_at > timezone.now()
        )


class DojoApplication(BackgroundCheckMixin, models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    applicant_phone = models.CharField(max_length=30, blank=True, default="")
    applicant_account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Set when an already-logged-in user submitted this application, so approval "
                  "(approve_and_provision_owner) can promote their existing account via "
                  "accounts.provisioning.attach_role instead of provisioning a disconnected new one.",
    )
    area = models.CharField(max_length=200, help_text="City/area where the dojo would run.")
    preferred_schedule = models.CharField(max_length=200, blank=True, default="", help_text='e.g. "Saturday mornings"')
    proposed_venue = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField(blank=True, default="")
    consent = models.BooleanField(default=False, help_text="Understands sessions are free and volunteer-run.")
    background_check_consent = models.BooleanField(
        default=False,
        help_text="Understands a Belgian criminal record extract (model 2, Artikel 596.2) will be required, "
                  "since a dojo's lead coach works directly with minors.",
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)

    # A ForeignKey: one owner can be provisioned/promoted by several
    # applications (one per dojo they start).
    provisioned_owner = models.ForeignKey(
        "accounts.DojoOwner", on_delete=models.SET_NULL, null=True, blank=True, related_name="applications",
        help_text="Set by approve_and_provision_owner. Lets a later background-check renewal "
                  "(validate_background_check, re-run on this same row) sync the new expiry "
                  "back onto the account that logs in with it.",
    )

    class Meta:
        permissions = [
            ("can_review_background_checks", "Can review background check documents"),
        ]

    def __str__(self):
        return f"{self.applicant_name} - {self.area}"


class MentorApplication(BackgroundCheckMixin, models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    VOLUNTEER_MENTOR = "volunteer_mentor"
    OTHER = "other"
    ROLE_CHOICES = [
        (VOLUNTEER_MENTOR, "Volunteer mentor"),
        (OTHER, "Something else (board, events, comms)"),
    ]

    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    applicant_phone = models.CharField(max_length=30, blank=True, default="")
    applicant_account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Set when an already-logged-in user submitted this application, so approval "
                  "(approve_and_provision_helper) can promote their existing account via "
                  "accounts.provisioning.attach_role instead of provisioning a disconnected new one.",
    )
    dojo = models.ForeignKey(
        "dojos.Dojo", on_delete=models.SET_NULL, null=True, blank=True, related_name="mentor_applications",
        help_text="Blank if the applicant is open to any dojo.",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=VOLUNTEER_MENTOR)
    about = models.TextField(blank=True, default="", help_text="Applicant's skills/interests.")
    background_check_consent = models.BooleanField(
        default=False,
        help_text="Understands a Belgian criminal record extract (model 2, Artikel 596.2) will be required "
                  "before working directly with minors.",
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)

    # A ForeignKey: one helper can be approved for several dojos, one
    # application each (see dojos.DojoMembership).
    provisioned_helper = models.ForeignKey(
        "accounts.HelperAccount", on_delete=models.SET_NULL, null=True, blank=True, related_name="applications",
        help_text="Set by approve_and_provision_helper. Lets a later background-check renewal "
                  "(validate_background_check, re-run on this same row) sync the new expiry "
                  "back onto the account that logs in with it.",
    )

    def __str__(self):
        return f"{self.applicant_name} ({self.get_role_display()})"
