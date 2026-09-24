from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError

MARKDOWN_HELP_TEXT = "Supports basic Markdown — # headings, **bold**, *italic*, links, lists."


class EventQuerySet(models.QuerySet):
    def visible(self):
        """What the public site (listings, the homepage widget, a dojo's own
        page) may show: not draft, and only for an `active` dojo — a draft,
        dormant or archived dojo's events are hidden with it. Both stay fully
        readable by the dojo's team via its admin events list; this only
        governs the public-facing side."""
        return self.exclude(status=Event.DRAFT).filter(dojo__status="active")


class Event(models.Model):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (OPEN, "Open"),
        (CLOSED, "Closed"),
    ]

    name = models.CharField(max_length=200)
    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=DRAFT,
        help_text="Draft: hidden from the public site while it's being put together. "
                  "Open: visible, registrations open. Closed: visible, registrations closed — "
                  "set manually, normally once attendance for the session has been checked."
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    places = models.IntegerField()

    location = models.PointField(srid=4326, null=True, blank=True, spatial_index=False)
    venue_name = models.CharField(max_length=200, blank=True, default="", help_text='e.g. "Ghent Public Library"')
    image = models.ImageField(
        upload_to="events/", null=True, blank=True,
        help_text="Banner shown on the homepage's Upcoming sessions card.",
    )

    description = models.TextField(blank=True, default="", help_text=MARKDOWN_HELP_TEXT)
    min_age = models.PositiveSmallIntegerField(null=True, blank=True)
    max_age = models.PositiveSmallIntegerField(null=True, blank=True)
    team = models.ManyToManyField(
        "dojos.DojoMembership", blank=True, related_name="events",
        help_text="Who ran (or will run) this session: members of the dojo's team.",
    )
    pathways = models.ManyToManyField(
        "pathways.Pathway", blank=True, related_name="events",
        help_text="The pathways this session covers (optional; shown on its public page). "
                  "Pre-filled from the dojo's; registrations pre-select these.",
    )

    participants = models.ManyToManyField("accounts.Participant", through="Registration")

    objects = EventQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.dojo})"

    @property
    def places_left(self):
        confirmed = self.registration_set.filter(waiting_list=False).count()
        return self.places - confirmed

    @property
    def registration_open(self):
        return self.status == self.OPEN


class Registration(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    participant = models.ForeignKey("accounts.Participant", on_delete=models.CASCADE)
    waiting_list = models.BooleanField()
    position = models.IntegerField()

    # Tri-state: None = not yet marked, True = present, False = absent.
    attended = models.BooleanField(null=True, blank=True)
    pathways = models.ManyToManyField(
        "pathways.Pathway", blank=True, related_name="registrations",
        help_text="What this ninja works on at this session — usually a subset of the event's "
                  "pathways, which it's pre-filled from.",
    )

    class Meta:
        # `position` is the event's own first-come-first-served queue —
        # see events.views.event_signup, which assigns it sequentially and
        # uses it to decide who's confirmed vs waitlisted.
        ordering = ["position"]
        unique_together = [("event", "participant")]


class Belt(models.Model):
    """A ninja's proficiency level: how skilled they are, not how often they
    came (that's a milestone Badge). One overall track, ordered by `level`;
    not linked to pathways (yet). A ninja's belts are an append-only history
    (NinjaBelt) and their current belt is the highest level in it."""

    name = models.CharField(max_length=100, help_text='e.g. "Yellow belt".')
    level = models.PositiveSmallIntegerField(unique=True, help_text="Order on the track: 1 is the first belt.")
    colour = models.CharField(max_length=7, blank=True, default="", help_text='Hex colour for the belt swatch, e.g. "#f5c518".')
    requirements = models.TextField(blank=True, default="", help_text="What a ninja must be able to do to get this belt.")
    icon = models.ImageField(upload_to="belts/", null=True, blank=True)

    class Meta:
        ordering = ["level"]

    def __str__(self):
        return self.name


class Badge(models.Model):
    """An award a ninja can achieve: a one-off ("did the thing", e.g.
    attended a CoderDojo for Girls session) or a milestone reached by a
    count of sessions attended (e.g. the attendance wristbands). A
    milestone can optionally also grant a belt when it's reached."""

    ONE_OFF = "one_off"
    MILESTONE = "milestone"
    KIND_CHOICES = [(ONE_OFF, "One-off"), (MILESTONE, "Milestone")]

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=ONE_OFF)
    description = models.CharField(max_length=300, blank=True, default="")
    criteria = models.CharField(
        max_length=200, blank=True, default="", help_text='One-off: what earns it, e.g. "Attend a CoderDojo for Girls session."',
    )
    threshold = models.PositiveIntegerField(
        null=True, blank=True, help_text="Milestone: how many sessions a ninja must attend to reach it.",
    )
    grants_belt = models.ForeignKey(
        Belt, on_delete=models.SET_NULL, null=True, blank=True, related_name="granted_by_badges",
        help_text="Milestone (optional): reaching it also grants this belt.",
    )
    icon = models.ImageField(upload_to="awards/", null=True, blank=True)

    class Meta:
        ordering = ["kind", "threshold", "name"]

    def __str__(self):
        return f"{self.name} ({self.threshold})" if self.kind == self.MILESTONE else self.name

    def clean(self):
        if self.kind == self.MILESTONE and not self.threshold:
            raise ValidationError({"threshold": "A milestone badge needs a threshold."})
        if self.kind == self.ONE_OFF and (self.threshold or self.grants_belt_id):
            raise ValidationError("Only milestone badges have a threshold or grant a belt.")


class NinjaBadge(models.Model):
    """One ninja's progress on one badge. A one-off is earned or not; a
    milestone tracks attended sessions toward its threshold (see
    events.awards.sync_milestones) and is earned once it's reached."""

    participant = models.ForeignKey("accounts.Participant", on_delete=models.CASCADE, related_name="badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="ninja_badges")

    earned_date = models.DateField(null=True, blank=True, help_text="Blank if still in progress.")
    progress_current = models.PositiveIntegerField(null=True, blank=True, help_text="Milestone only.")
    progress_total = models.PositiveIntegerField(null=True, blank=True, help_text="Milestone only.")

    class Meta:
        unique_together = [("participant", "badge")]

    def __str__(self):
        return f"{self.participant} - {self.badge}"


class NinjaBelt(models.Model):
    """One belt a ninja reached: an append-only history, never overwritten
    (the current belt is the highest level). Only an active champion or
    mentor can award one (events.awards.award_belt), recorded as both the
    account and the membership they acted in, plus that membership's role
    at the time (a role can change later, e.g. a champion handover).

    Both links are required when a belt is awarded; they're nullable only so
    the history survives the account or dojo being deleted."""

    participant = models.ForeignKey("accounts.Participant", on_delete=models.CASCADE, related_name="belts")
    belt = models.ForeignKey(Belt, on_delete=models.PROTECT, related_name="ninja_belts")
    awarded_on = models.DateField()
    awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="belts_awarded",
    )
    awarded_as_membership = models.ForeignKey(
        "dojos.DojoMembership", on_delete=models.SET_NULL, null=True, related_name="belts_awarded",
    )
    awarded_as_role = models.CharField(max_length=20, blank=True, default="", help_text="The membership's role when awarding.")
    note = models.CharField(max_length=300, blank=True, default="", help_text="Optional: what the ninja showed.")

    class Meta:
        ordering = ["-awarded_on", "-id"]

    def __str__(self):
        return f"{self.participant} - {self.belt}"

    @property
    def awarded_by_label(self):
        """ "Jan, as mentor of CoderDojo Ghent" (or as much of it as survives)."""
        membership = self.awarded_as_membership
        who = membership.name if membership else (self.awarded_by.get_full_name() if self.awarded_by else "")
        if not membership:
            return who
        role = dict(membership.ROLE_CHOICES).get(self.awarded_as_role or membership.role, "").lower()
        return f"{who}, as {role} of {membership.dojo.name}"
