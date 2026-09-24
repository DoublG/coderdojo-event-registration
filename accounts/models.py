from datetime import date

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models
from django.utils import timezone


class User(AbstractUser):
    """Every login: a normal adult account or a ninja's own login
    (account_type). Parents are adult accounts with Guardianship rows to
    their ninjas. DojoOwner/HelperAccount below are the last role
    subclasses; the redesign replaces them with dojo memberships
    (DATA_MODEL.md §10)."""

    must_change_password = models.BooleanField(
        default=False,
        help_text="Forces a password change on next login — set when an admin provisions an "
                  "account (DojoOwner, HelperAccount) with a temporary password. Enforced by "
                  "accounts.middleware.ForcePasswordChangeMiddleware.",
    )

    # Only ever set for DojoOwner/HelperAccount, whose applications
    # (applications.DojoApplication/MentorApplication) went through the
    # Belgian background-check pipeline — mirrors must_change_password in
    # living on the base User even though it's only meaningful for those
    # two roles. Parent and ninja accounts never touch these fields; they never
    # go through that pipeline at all (see applications.models.BackgroundCheckMixin).
    background_check_required = models.BooleanField(
        default=False,
        help_text="Set at provisioning time from the linked application's "
                  "background_check_required (age-based — see BACKGROUND_CHECK_MINIMUM_AGE). "
                  "When true, login is refused once background_check_expires_at lapses — see "
                  "accounts.backends and accounts.middleware.BackgroundCheckMiddleware — until "
                  "a reviewer validates a fresh one (applications.admin.validate_background_check "
                  "syncs the new expiry back here).",
    )
    background_check_expires_at = models.DateTimeField(null=True, blank=True)

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
        return not self.background_check_required or (
            self.background_check_expires_at is not None and self.background_check_expires_at > timezone.now()
        )


class DojoOwner(User):
    """Marks an adult account as an approved dojo owner (from an approved
    DojoApplication). Being a dojo's champion is a dojos.DojoMembership;
    this role subclass goes away in redesign phase 3."""

    class Meta:
        verbose_name = "dojo owner"
        verbose_name_plural = "dojo owners"

    def __str__(self):
        return self.get_username()


class HelperAccount(User):
    """Marks an adult account as an approved mentor (from an approved
    MentorApplication): what lets it ask to join, or be added to, a dojo's
    team (dojos.access.is_approved_mentor). The team roles themselves live
    on dojos.DojoMembership. Replaced by the account-level Application in
    redesign phase 3."""

    class Meta:
        verbose_name = "helper account"
        verbose_name_plural = "helper accounts"

    def __str__(self):
        return self.get_username()


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
