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
    preferred_language = models.CharField(
        max_length=10, choices=settings.LANGUAGES, blank=True, default="",
        help_text="The language mails are sent in. Set from the site's language at sign-up; "
                  "empty means the default (English).",
    )
    postal_code = models.CharField(
        max_length=4, blank=True, default="",
        help_text="Belgian postcode where the family lives (geo.Municipality.postal_code). Used to "
                  "tell families about dojos and sessions near them, never shown publicly.",
    )

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


NINJA_MIN_AGE, NINJA_MAX_AGE = 7, 17


def age_on(date_of_birth, day):
    had_birthday = (day.month, day.day) >= (date_of_birth.month, date_of_birth.day)
    return day.year - date_of_birth.year - (0 if had_birthday else 1)


def ninja_birth_date_error(date_of_birth):
    """A user-facing message if `date_of_birth` doesn't make a ninja
    (a child aged 7–17 today), else None. A missing date is fine here —
    whether it's required is up to the form."""
    if date_of_birth is None:
        return None
    if not NINJA_MIN_AGE <= age_on(date_of_birth, date.today()) <= NINJA_MAX_AGE:
        return f"Ninjas are {NINJA_MIN_AGE} to {NINJA_MAX_AGE} years old — check the date of birth."
    return None


class NinjaQuerySet(models.QuerySet):
    def of_guardian(self, user):
        """The ninjas `user` is a parent/guardian of (via Guardianship)."""
        return self.filter(guardianships__guardian=user).distinct()

    def signable_by(self, user):
        """The ninjas `user` can sign up for sessions: an adult account's
        children, or a ninja's own login itself (DATA_MODEL.md §17)."""
        if user.is_ninja:
            return self.filter(account=user)
        return self.of_guardian(user)


class Ninja(models.Model):
    """A child aged 7–17 who visits a dojo (DATA_MODEL.md nomenclature).
    Not a login: a parent can give them one (`account`, a ninja-type User).
    The age rule applies when a date of birth is entered or changed, so a
    ninja who has since turned 18 can still be edited."""

    GIRL = "girl"
    BOY = "boy"
    OTHER = "other"
    UNSPECIFIED = "unspecified"
    GENDER_CHOICES = [(GIRL, "Girl"), (BOY, "Boy"), (OTHER, "Other"), (UNSPECIFIED, "Prefer not to say")]

    name = models.CharField(max_length=200)
    gender = models.CharField(
        max_length=12, choices=GENDER_CHOICES, default=UNSPECIFIED,
        help_text="Optional, never shown publicly. Used to let families know about girls' sessions "
                  "(Event.audience), never to restrict who can sign up.",
    )
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
        "dojos.Dojo", on_delete=models.SET_NULL, null=True, blank=True, related_name="home_ninjas"
    )
    member_since = models.DateField(null=True, blank=True)
    allergies_notes = models.TextField(blank=True, default="", help_text="Allergies or other notes for mentors.")
    photo = models.ImageField(upload_to="participants/", null=True, blank=True)

    objects = NinjaQuerySet.as_manager()

    def __str__(self):
        return self.name

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        return age_on(self.date_of_birth, date.today())

    def clean(self):
        stored = Ninja.objects.filter(pk=self.pk).values_list("date_of_birth", flat=True).first() if self.pk else None
        if self.date_of_birth != stored and (error := ninja_birth_date_error(self.date_of_birth)):
            raise ValidationError({"date_of_birth": error})

    @property
    def youth_mentor_memberships(self):
        """The dojo teams this child is an active youth mentor on (through
        their own login), dojo loaded."""
        if not self.account_id:
            return []
        return list(self.account.dojo_memberships.filter(role="youth_mentor", status="active").select_related("dojo"))

    @property
    def current_belt(self):
        """The highest belt in this ninja's belt history (events.NinjaBelt),
        or None. Reads `belts.all()` so a prefetch of `belts__belt` covers it."""
        awards = list(self.belts.all())
        return max(awards, key=lambda a: a.belt.level).belt if awards else None


class GuardianshipManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("guardian", "ninja")


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
    ninja = models.ForeignKey(Ninja, on_delete=models.CASCADE, related_name="guardianships")
    relation = models.CharField(max_length=20, choices=RELATION_CHOICES, default=PARENT)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = GuardianshipManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["guardian", "ninja"], name="unique_guardianship")]

    def __str__(self):
        return f"{self.guardian} → {self.ninja}"


class OrganisationRoleManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("account")


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

    objects = OrganisationRoleManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "role"], name="unique_organisation_role")]

    def __str__(self):
        return f"{self.account} ({self.get_role_display()})"

    def clean(self):
        if self.account_id and self.account.is_ninja:
            raise ValidationError("Only an adult account can have an organisation role.")
