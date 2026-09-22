from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.db.models import Case, When

from geo.models import AdministrativeBoundary, Municipality

MARKDOWN_HELP_TEXT = "Supports basic Markdown — # headings, **bold**, *italic*, links, lists."


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
    icon = models.ImageField(
        upload_to="dojos/", null=True, blank=True,
        help_text="Round icon shown at the top of the dojo page, next to its name.",
    )

    tagline = models.TextField(
        blank=True, default="",
        help_text=f"Shown at the top of the dojo page, between the title and the buttons. {MARKDOWN_HELP_TEXT}",
    )
    description = models.TextField(
        blank=True, default="",
        help_text=f"Shown further down the dojo page, above the team. {MARKDOWN_HELP_TEXT}",
    )
    schedule_description = models.CharField(
        max_length=200, blank=True, default="", help_text='e.g. "Every 2nd Saturday"'
    )
    min_age = models.PositiveSmallIntegerField(null=True, blank=True)
    max_age = models.PositiveSmallIntegerField(null=True, blank=True)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    visit_notes = models.TextField(
        blank=True, default="",
        help_text=f"Optional extra info for the Visit us section — parking, entrance, "
                  f"accessibility, whatever this chapter needs to add. {MARKDOWN_HELP_TEXT}",
    )

    def __str__(self):
        return f"{self.name} ({self.municipality})"


class MentorQuerySet(models.QuerySet):
    def public(self):
        """Excludes mentors who've opted out of appearing on the public
        team pages (dojo page, team page, homepage) — see Mentor.is_public."""
        return self.filter(is_public=True)

    def lead_coach_first(self):
        """A dojo's LEAD_COACH is always shown first — see the Mentor
        docstring for why that's the one role tied to a real DojoOwner
        login rather than an optional helper account."""
        return self.public().order_by(Case(When(role=Mentor.LEAD_COACH, then=0), default=1), "name")


class Mentor(models.Model):
    """A public team-page profile. Exactly one role per dojo carries real
    operational authority — LEAD_COACH — and that one must be linked to the
    dojo's own DojoOwner login (owner_account); it's always shown first.
    CHAMPION is a distinct, separate role: an honorary/promoted status (e.g.
    a stand-out ninja recognised by someone with admin rights) with no
    account requirement of its own. Every non-lead-coach role (champion,
    ninja, volunteer, board — the "helpers") may optionally be linked to
    whichever of the three account types actually holds their login:
    a HelperAccount (a plain adult volunteer), a Guardian (a parent who
    helps out at their own kid's dojo), or a ChildAccount (a ninja). At
    most one of the four account fields may be set; see clean()."""

    LEAD_COACH = "lead_coach"
    CHAMPION = "champion"
    NINJA = "ninja"
    VOLUNTEER = "volunteer"
    BOARD = "board"
    ROLE_CHOICES = [
        (LEAD_COACH, "Lead Coach"),
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
    email = models.EmailField(blank=True, default="", help_text="Shown on their team detail page, if set.")
    bio = models.TextField(blank=True, default="")
    photo = models.ImageField(upload_to="mentors/", null=True, blank=True)
    joined_date = models.DateField(null=True, blank=True)
    sessions_run = models.PositiveIntegerField(null=True, blank=True)
    focus_areas = models.CharField(
        max_length=300, blank=True, default="",
        help_text="Comma-separated, board members only, e.g. \"Volunteer recruitment, Partnerships\"",
    )

    # Exactly one of these four should be set — see the class docstring
    # and clean(). All nullable/optional: plenty of mentor profiles (e.g.
    # seed/demo data, or a dojo's ninjas in general) have no login at all.
    owner_account = models.OneToOneField(
        "accounts.DojoOwner", on_delete=models.SET_NULL, null=True, blank=True, related_name="mentor_profile",
        help_text="Required for the LEAD_COACH mentor — must be this mentor's dojo's own owner login.",
    )
    helper_account = models.OneToOneField(
        "accounts.HelperAccount", on_delete=models.SET_NULL, null=True, blank=True, related_name="mentor_profile",
    )
    guardian_account = models.OneToOneField(
        "accounts.Guardian", on_delete=models.SET_NULL, null=True, blank=True, related_name="mentor_profile",
        help_text="A parent helping out at their own child's dojo.",
    )
    child_account = models.OneToOneField(
        "accounts.ChildAccount", on_delete=models.SET_NULL, null=True, blank=True, related_name="mentor_profile",
        help_text="A ninja's own login — only meaningful once they've been promoted to CHAMPION.",
    )

    is_public = models.BooleanField(
        default=True, help_text="Uncheck to opt this person out of the public team pages."
    )

    objects = MentorQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"

    def clean(self):
        linked_accounts = [
            f for f in ("owner_account", "helper_account", "guardian_account", "child_account")
            if getattr(self, f"{f}_id")
        ]
        if len(linked_accounts) > 1:
            raise ValidationError("A mentor can be linked to only one account.")

        if self.role == self.LEAD_COACH:
            if not self.owner_account_id:
                raise ValidationError("The Lead Coach must be linked to the dojo's owner account.")
            if self.dojo_id and self.owner_account.dojos.filter(id=self.dojo_id).count() == 0:
                raise ValidationError("The linked owner account must own this mentor's dojo.")
        elif self.owner_account_id:
            raise ValidationError("Only the Lead Coach can be linked to a dojo owner account.")
