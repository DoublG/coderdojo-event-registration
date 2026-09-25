from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.db.models import Case, When
from django.utils.translation import gettext_lazy as _

from geo.models import AdministrativeBoundary, Municipality

MARKDOWN_HELP_TEXT = "Supports basic Markdown — # headings, **bold**, *italic*, links, lists."


class DojoQuerySet(models.QuerySet):
    def public(self):
        """What the public site may show: `active` dojos only. Draft,
        dormant and archived dojos stay reachable for their own team (the
        admin area) and in ninjas' own history, never in public listings.
        Organisation dojos (Dojo.kind) are never listed either: only their
        events are public (DATA_MODEL.md §12)."""
        return self.filter(status=Dojo.ACTIVE, kind=Dojo.DOJO)

class DojoManager(models.Manager.from_queryset(DojoQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related("municipality")


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
    # Lifecycle (DATA_MODEL.md §10). A new dojo starts as a draft its
    # champion sets up; only `active` dojos (and their events) are public.
    DRAFT = "draft"
    ACTIVE = "active"
    DORMANT = "dormant"
    ARCHIVED = "archived"
    STATUS_CHOICES = [(DRAFT, _("Draft")), (ACTIVE, _("Active")), (DORMANT, _("Dormant")), (ARCHIVED, _("Archived"))]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    # An organisation dojo (DATA_MODEL.md §12) runs the organisation's own
    # events (CoderDojo Girlz, Coolest Projects). It has a team and an admin
    # area like any dojo, and must be `active` for its events to show, but
    # it's never listed itself: no dojo finder, dojo page or dojo pickers.
    DOJO = "dojo"
    ORGANISATION = "organisation"
    KIND_CHOICES = [(DOJO, _("Dojo")), (ORGANISATION, _("Organisation"))]
    kind = models.CharField(
        max_length=12, choices=KIND_CHOICES, default=DOJO,
        help_text="Organisation: runs the organisation's own events. Never shown in the dojo finder or "
                  "as a dojo page; its events say “Organised by” instead of linking to it.",
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="The approved champion who created this dojo.",
    )
    pathways = models.ManyToManyField(
        "pathways.Pathway", blank=True, related_name="dojos",
        help_text="The pathways this dojo provides (optional). New events pre-select these.",
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

    objects = DojoManager()

    def __str__(self):
        return f"{self.name} ({self.municipality})"

    @property
    def is_public(self):
        return self.status == self.ACTIVE and self.kind == self.DOJO

    @property
    def is_organisation(self):
        return self.kind == self.ORGANISATION

    @property
    def champion_membership(self):
        return self.memberships.filter(role=DojoMembership.CHAMPION, status=DojoMembership.ACTIVE).first()

    @property
    def champion(self):
        """The dojo's champion (owner) account, or None."""
        membership = self.champion_membership
        return membership.user if membership else None


class DojoMembershipQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=DojoMembership.ACTIVE)

    def managers(self):
        """Active champion/mentor memberships: the people who run the dojo
        (admin access, notifications). Youth mentors are on the team, but
        never manage it."""
        return self.active().filter(role__in=DojoMembership.MANAGER_ROLES)

    def for_team_page(self):
        """What a dojo's public team listing shows: active members who
        haven't opted out, the champion first, then mentors, then youth
        mentors, each alphabetically."""
        return (
            self.active()
            .filter(user__show_on_team_pages=True)
            .select_related("user")
            .order_by(
                Case(
                    When(role=DojoMembership.CHAMPION, then=0),
                    When(role=DojoMembership.MENTOR, then=1),
                    default=2,
                ),
                "user__first_name", "user__username",
            )
        )


class DojoMembershipManager(models.Manager.from_queryset(DojoMembershipQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related("user", "dojo")


class DojoMembership(models.Model):
    """One account's place on one dojo's team (DATA_MODEL.md §10): its role
    there and where it is in the join → leave lifecycle. Replaces Dojo.owner
    and the old Mentor profile table — the team-page profile itself (name,
    title, bio, photo) lives on the account and is shared by every dojo the
    person is on.

    Roles: `champion` (the dojo's owner — exactly one active per dojo),
    `mentor` (an adult helper) and `youth_mentor` (a ninja helping run
    sessions, promoted by a champion/mentor of the same dojo). Rows are
    never deleted when someone leaves: they go `dormant`, so past events'
    teams (Event.team) keep their history."""

    CHAMPION = "champion"
    MENTOR = "mentor"
    YOUTH_MENTOR = "youth_mentor"
    ROLE_CHOICES = [(CHAMPION, _("Champion")), (MENTOR, _("Mentor")), (YOUTH_MENTOR, _("Youth mentor"))]
    MANAGER_ROLES = (CHAMPION, MENTOR)

    REQUESTED = "requested"
    ACTIVE = "active"
    DORMANT = "dormant"
    STATUS_CHOICES = [(REQUESTED, _("Requested")), (ACTIVE, _("Active")), (DORMANT, _("Dormant"))]

    dojo = models.ForeignKey(Dojo, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="dojo_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Who asked (the mentor themselves) or added them (a champion/mentor).",
    )
    decided_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="The champion/mentor who accepted or declined a join request.",
    )
    promoted_by = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Youth mentors only: the champion/mentor membership that promoted them.",
    )
    joined_at = models.DateTimeField(null=True, blank=True, help_text="When this membership (last) became active.")
    left_at = models.DateTimeField(null=True, blank=True, help_text="When it became dormant; empty while active.")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DojoMembershipManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dojo", "user"], name="unique_membership_per_dojo")]

    def __str__(self):
        return f"{self.name} ({self.get_role_display()}, {self.dojo.name})"

    def clean(self):
        if self.role == self.YOUTH_MENTOR:
            if not self.user.is_ninja:
                raise ValidationError(_("Only a ninja account can be a youth mentor."))
        elif self.user.is_ninja:
            raise ValidationError(_("A ninja account can only be a youth mentor."))
        if self.role == self.CHAMPION and self.status == self.ACTIVE:
            others = DojoMembership.objects.filter(
                dojo_id=self.dojo_id, role=self.CHAMPION, status=self.ACTIVE,
            ).exclude(pk=self.pk)
            if others.exists():
                raise ValidationError(_("This dojo already has an active champion."))
        if self.promoted_by_id:
            promoter = self.promoted_by
            if promoter.dojo_id != self.dojo_id or promoter.role not in self.MANAGER_ROLES:
                raise ValidationError(_("A youth mentor must be promoted by a champion or mentor of the same dojo."))

    # Display fields for the team pages and shared avatar partial — the
    # profile itself lives on the account (shared by all its dojos).
    @property
    def name(self):
        return self.user.team_name

    @property
    def title(self):
        return self.user.title

    @property
    def bio(self):
        return self.user.bio

    @property
    def photo(self):
        return self.user.photo

    @property
    def email(self):
        return "" if self.user.is_ninja else self.user.email

    @property
    def sessions_run(self):
        """Past sessions this member was on the team of."""
        from django.utils import timezone

        return self.events.filter(start_time__lt=timezone.now()).count()
