from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import User

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


class ApplicationManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("account")


class Application(models.Model):
    """An account asking to become a **mentor** (help at dojos) or a
    **champion** (start and run a dojo) — once per account and kind, not
    per dojo (DATA_MODEL.md §10). Approval needs the applicant's account to
    have a valid background check (accounts.User.background_check_valid);
    an approved mentor can then ask to join any dojo's team (or be added),
    an approved champion can create a dojo. See applications.services for
    the flow and applications.admin for the review actions."""

    MENTOR = "mentor"
    CHAMPION = "champion"
    KIND_CHOICES = [(MENTOR, _("Mentor")), (CHAMPION, _("Champion (start a dojo)"))]

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [(PENDING, _("Pending")), (APPROVED, _("Approved")), (REJECTED, _("Rejected"))]

    VOLUNTEER_MENTOR = "volunteer_mentor"
    OTHER = "other"
    MENTOR_ROLE_CHOICES = [
        (VOLUNTEER_MENTOR, "Volunteer mentor"),
        (OTHER, "Something else (board, events, comms)"),
    ]

    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    # Mentor applications.
    dojo = models.ForeignKey(
        "dojos.Dojo", on_delete=models.SET_NULL, null=True, blank=True, related_name="applications",
        help_text="Mentor applications: the dojo they'd like to help at (blank = any). Approval "
                  "files a join request there.",
    )
    mentor_role = models.CharField(max_length=20, choices=MENTOR_ROLE_CHOICES, blank=True, default="")

    # Champion applications.
    area = models.CharField(max_length=200, blank=True, default="", help_text="City/area where the dojo would run.")
    preferred_schedule = models.CharField(max_length=200, blank=True, default="", help_text='e.g. "Saturday mornings"')
    proposed_venue = models.CharField(max_length=200, blank=True, default="")

    message = models.TextField(blank=True, default="", help_text="Skills, interests, experience, anything useful.")
    consent = models.BooleanField(default=False, help_text="Champions: understands sessions are free and volunteer-run.")
    background_check_consent = models.BooleanField(
        default=False,
        help_text="Understands a Belgian criminal record extract (model 2, Artikel 596.2) is required "
                  "before working with minors.",
    )

    objects = ApplicationManager()

    class Meta:
        permissions = [
            ("can_review_background_checks", "Can review background check documents"),
        ]
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.account} — {self.get_kind_display()} ({self.get_status_display()})"


class BackgroundCheckHistoryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("account")


class BackgroundCheckHistory(models.Model):
    """Append-only audit log of background-check decisions: one row per
    validation or rejection of an account's check, recording who reviewed
    it and when. Nothing reads it to decide access — the current check on
    accounts.User does that. Never stores the document itself (that's
    deleted as soon as the decision is made)."""

    VALIDATED = "validated"
    REJECTED = "rejected"
    DECISION_CHOICES = [(VALIDATED, "Validated"), (REJECTED, "Rejected")]

    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="background_check_history",
    )
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    reviewed_at = models.DateTimeField()
    requested_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Validated checks only.")
    note = models.TextField(blank=True, default="", help_text="Optional reviewer remark — never the document.")

    objects = BackgroundCheckHistoryManager()

    class Meta:
        ordering = ["-reviewed_at"]
        verbose_name_plural = "background check history"

    def __str__(self):
        return f"{self.account} — {self.get_decision_display()} {self.reviewed_at:%Y-%m-%d}"


class BackgroundCheck(User):
    """Admin-only proxy over accounts.User: the reviewers' "Background checks"
    list (applications.admin). Same rows, no extra table."""

    class Meta:
        proxy = True
        verbose_name = "background check"
        verbose_name_plural = "background checks"
