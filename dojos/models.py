from django.contrib.gis.db import models

from geo.models import AdministrativeBoundary, Municipality


class Dojo(models.Model):
    name = models.CharField(max_length=200)
    municipality = models.ForeignKey(Municipality, on_delete=models.CASCADE, null=True, blank=True)
    province = models.ForeignKey(
        AdministrativeBoundary,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"kind": AdministrativeBoundary.PROVINCE},
        related_name="dojos",
    )
    address = models.CharField(max_length=200, blank=True, default="")
    location = models.PointField(srid=4326, null=True, blank=True, spatial_index=False)
    owner = models.ForeignKey(
        "accounts.DojoOwner", on_delete=models.SET_NULL, null=True, blank=True, related_name="dojos"
    )

    description = models.TextField(blank=True, default="")
    schedule_description = models.CharField(
        max_length=200, blank=True, default="", help_text='e.g. "Every 2nd Saturday"'
    )
    min_age = models.PositiveSmallIntegerField(null=True, blank=True)
    max_age = models.PositiveSmallIntegerField(null=True, blank=True)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")

    quote = models.TextField(blank=True, default="")
    quote_author = models.ForeignKey(
        "Mentor", on_delete=models.SET_NULL, null=True, blank=True, related_name="quoted_on_dojos"
    )

    def __str__(self):
        return f"{self.name} ({self.municipality})"


class Mentor(models.Model):
    CHAMPION = "champion"
    NINJA = "ninja"
    VOLUNTEER = "volunteer"
    BOARD = "board"
    ROLE_CHOICES = [
        (CHAMPION, "Dojo champion"),
        (NINJA, "Ninja mentor"),
        (VOLUNTEER, "Volunteer mentor"),
        (BOARD, "Board member"),
    ]

    name = models.CharField(max_length=200)
    dojo = models.ForeignKey(
        Dojo, on_delete=models.SET_NULL, null=True, blank=True, related_name="mentors",
        help_text="Left blank for board members, who work across dojos.",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    title = models.CharField(max_length=200, blank=True, default="", help_text='e.g. "Software engineer"')
    bio = models.TextField(blank=True, default="")
    photo = models.ImageField(upload_to="mentors/", null=True, blank=True)
    joined_date = models.DateField(null=True, blank=True)
    sessions_run = models.PositiveIntegerField(null=True, blank=True)
    focus_areas = models.CharField(
        max_length=300, blank=True, default="",
        help_text="Comma-separated, board members only, e.g. \"Volunteer recruitment, Partnerships\"",
    )

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"
