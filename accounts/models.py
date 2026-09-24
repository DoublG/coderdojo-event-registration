from datetime import date

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from applications.storage import get_private_storage


class User(AbstractUser):
    """Every login: a normal adult account or a ninja's own login
    (account_type). Parents are adult accounts with Guardianship rows to
    their ninjas; champions and mentors are adult accounts with dojo
    memberships (dojos.DojoMembership) and an approved application
    (applications.Application). There are no role subclasses
    (DATA_MODEL.md §10)."""

    must_change_password = models.BooleanField(
        default=False,
        help_text="Forces a password change on next login (e.g. set by an admin who reset it). "
                  "Enforced by accounts.middleware.ForcePasswordChangeMiddleware.",
    )

    # The account's *current* Belgian background check (uittreksel model 2,
    # Artikel 596.2 — see applications.models.ARTICLE_596_2_TEXT). Only
    # needed to become a champion or mentor: a parent using the site never
    # goes through it. Every review decision is also appended to
    # applications.BackgroundCheckHistory (who decided, when); the flow
    # itself lives in applications.services. A valid check is what lets
    # champion/mentor memberships grant dojo access (dojos.access) — a
    # lapsed one removes that access, never the login.
    CHECK_NOT_REQUESTED = "not_requested"
    CHECK_REQUESTED = "requested"
    CHECK_SUBMITTED = "submitted"
    CHECK_VALIDATED = "validated"
    CHECK_REJECTED = "rejected"
    CHECK_STATUS_CHOICES = [
        (CHECK_NOT_REQUESTED, "Not requested yet"),
        (CHECK_REQUESTED, "Requested — waiting on the account holder"),
        (CHECK_SUBMITTED, "Submitted — awaiting review"),
        (CHECK_VALIDATED, "Validated"),
        (CHECK_REJECTED, "Rejected"),
    ]
    background_check_status = models.CharField(
        max_length=20, choices=CHECK_STATUS_CHOICES, default=CHECK_NOT_REQUESTED,
    )
    background_check_token = models.UUIDField(
        null=True, blank=True, unique=True, editable=False,
        help_text="Set when a check is requested; builds the emailed upload link.",
    )
    background_check_document = models.FileField(
        upload_to="background_checks/", storage=get_private_storage, null=True, blank=True,
        help_text="The uploaded uittreksel uit het strafregister, model 2 (Artikel 596.2). Only "
                  "readable by a reviewer (applications.can_review_background_checks) via the "
                  "protected download view — never a public media URL. Deleted as soon as a "
                  "decision is made; only the decision is kept.",
    )
    background_check_requested_at = models.DateTimeField(null=True, blank=True)
    background_check_submitted_at = models.DateTimeField(null=True, blank=True)
    background_check_reviewed_at = models.DateTimeField(null=True, blank=True)
    background_check_expires_at = models.DateTimeField(
        null=True, blank=True, help_text="Set on validation; the check must be redone after this date.",
    )

    # The redesign's two account types (DATA_MODEL.md §10): a normal adult
    # account, or a ninja's own login. One table for both, so login and
    # every link to "an account" stay a single foreign key.
    ADULT = "adult"
    NINJA = "ninja"
    ACCOUNT_TYPE_CHOICES = [(ADULT, "Adult"), (NINJA, "Ninja")]
    account_type = models.CharField(max_length=10, choices=ACCOUNT_TYPE_CHOICES, default=ADULT)
    phone = models.CharField(max_length=30, blank=True, default="")

    # The team-page profile: shown wherever this person appears on a dojo's
    # team (dojos.DojoMembership), and shared by every dojo they're on.
    display_name = models.CharField(
        max_length=150, blank=True, default="",
        help_text="How this person is named on team pages; defaults to their full name.",
    )
    title = models.CharField(max_length=200, blank=True, default="", help_text='e.g. "Software engineer"')
    bio = models.TextField(blank=True, default="")
    photo = models.ImageField(upload_to="profiles/", null=True, blank=True)
    show_on_team_pages = models.BooleanField(
        default=True, help_text="Uncheck to keep this person off the public team pages.",
    )

    @property
    def is_ninja(self):
        return self.account_type == self.NINJA

    @property
    def team_name(self):
        """The name shown on team pages: display_name, else full name
        (first name only for a ninja), else the username."""
        if self.display_name:
            return self.display_name
        name = self.first_name if self.is_ninja else self.get_full_name()
        return name or self.get_username()

    @property
    def background_check_valid(self):
        """A validated check that hasn't expired — needed for champion/mentor
        dojo access (dojos.access)."""
        return (
            self.background_check_status == self.CHECK_VALIDATED
            and self.background_check_expires_at is not None
            and self.background_check_expires_at > timezone.now()
        )

    @property
    def background_check_can_upload(self):
        """Whether the account can upload a (new) document right now: a check
        was requested or rejected, or a validated one has expired."""
        if self.background_check_status in (self.CHECK_REQUESTED, self.CHECK_REJECTED):
            return True
        return self.background_check_status == self.CHECK_VALIDATED and not self.background_check_valid


class ParticipantQuerySet(models.QuerySet):
    def of_guardian(self, user):
        """The ninjas `user` is a parent/guardian of (via Guardianship)."""
        return self.filter(guardianships__guardian=user).distinct()


class Participant(models.Model):
    NEW = "new"
    SOME = "some"
    CONFIDENT = "confident"
    EXPERIENCE_CHOICES = [
        (NEW, "New to coding"),
        (SOME, "Some experience"),
        (CONFIDENT, "Confident"),
    ]

    name = models.CharField(max_length=200)
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ninja",
        limit_choices_to={"account_type": "ninja"},
        help_text="The child's own login (an account of type ninja) — set only if a "
                  "parent has allowed it.",
    )

    date_of_birth = models.DateField(null=True, blank=True)
    home_dojo = models.ForeignKey(
        "dojos.Dojo", on_delete=models.SET_NULL, null=True, blank=True, related_name="home_participants"
    )
    member_since = models.DateField(null=True, blank=True)
    experience_level = models.CharField(max_length=10, choices=EXPERIENCE_CHOICES, blank=True, default="")
    allergies_notes = models.TextField(blank=True, default="", help_text="Allergies or other notes for mentors.")
    photo = models.ImageField(upload_to="participants/", null=True, blank=True)

    objects = ParticipantQuerySet.as_manager()

    def __str__(self):
        return self.name

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        had_birthday = (today.month, today.day) >= (self.date_of_birth.month, self.date_of_birth.day)
        return years if had_birthday else years - 1

    @property
    def current_belt(self):
        """The highest belt in this ninja's belt history (events.NinjaBelt),
        or None. Reads `belts.all()` so a prefetch of `belts__belt` covers it."""
        awards = list(self.belts.all())
        return max(awards, key=lambda a: a.belt.level).belt if awards else None


class Guardianship(models.Model):
    """Links a parent's (adult) account to a ninja they're responsible for.
    Replaces the old Guardian account subclass: any adult account can have
    children, and a child can have more than one parent/guardian."""

    PARENT = "parent"
    LEGAL_GUARDIAN = "legal_guardian"
    OTHER = "other"
    RELATION_CHOICES = [(PARENT, "Parent"), (LEGAL_GUARDIAN, "Legal guardian"), (OTHER, "Other")]

    guardian = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="guardianships",
        limit_choices_to={"account_type": "adult"},
    )
    ninja = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="guardianships")
    relation = models.CharField(max_length=20, choices=RELATION_CHOICES, default=PARENT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["guardian", "ninja"], name="unique_guardianship")]

    def __str__(self):
        return f"{self.guardian} → {self.ninja}"


class OrganisationRole(models.Model):
    """Access to the organisation's management dashboards — for now the
    Django admin (DATA_MODEL.md §10, decision 4). Separate from being
    *listed* on the organisation's team page (content.OrganisationTeamMember):
    not everyone with access is listed, and vice versa.

    A role makes the account staff and puts it in the matching group, whose
    permissions are defined in accounts.organisation (kept in sync by the
    signals there — don't set is_staff or these groups by hand)."""

    BOARD = "board"
    ADMIN = "admin"
    ROLE_CHOICES = [(BOARD, "Board (read-only)"), (ADMIN, "Admin")]

    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organisation_roles",
        limit_choices_to={"account_type": "adult"},
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "role"], name="unique_organisation_role")]

    def __str__(self):
        return f"{self.account} ({self.get_role_display()})"

    def clean(self):
        if self.account_id and self.account.is_ninja:
            raise ValidationError("Only an adult account can have an organisation role.")
