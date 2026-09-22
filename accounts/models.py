from datetime import date

from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models


class User(AbstractUser):
    """Base user model, so role-specific accounts (DojoOwner, Guardian,
    ChildAccount, and future roles) can subclass it via multi-table
    inheritance while sharing the same login/auth machinery."""


class DojoOwner(User):
    class Meta:
        verbose_name = "dojo owner"
        verbose_name_plural = "dojo owners"

    def __str__(self):
        dojo_names = ", ".join(self.dojos.values_list("name", flat=True)) or "no dojos"
        return f"{self.get_username()} ({dojo_names})"


class Guardian(User):
    phone = models.CharField(max_length=30, blank=True, default="")

    class Meta:
        verbose_name = "guardian"
        verbose_name_plural = "guardians"

    def __str__(self):
        return self.get_username()


class ChildAccount(User):
    """A child's own login. Only created when their guardian has opted
    them in (see Participant.account) — most participants have none."""

    class Meta:
        verbose_name = "child account"
        verbose_name_plural = "child accounts"

    def __str__(self):
        return self.get_username()


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
    guardian = models.ForeignKey(Guardian, on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    account = models.OneToOneField(
        ChildAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="participant",
        help_text="Set only if the guardian has allowed this child to have their own login.",
    )

    date_of_birth = models.DateField(null=True, blank=True)
    home_dojo = models.ForeignKey(
        "dojos.Dojo", on_delete=models.SET_NULL, null=True, blank=True, related_name="home_participants"
    )
    member_since = models.DateField(null=True, blank=True)
    experience_level = models.CharField(max_length=10, choices=EXPERIENCE_CHOICES, blank=True, default="")
    allergies_notes = models.TextField(blank=True, default="", help_text="Allergies or other notes for mentors.")
    photo = models.ImageField(upload_to="participants/", null=True, blank=True)

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
