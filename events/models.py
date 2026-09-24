from django.contrib.gis.db import models

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
    pathway = models.ForeignKey(
        "pathways.Pathway", on_delete=models.SET_NULL, null=True, blank=True, related_name="registrations"
    )

    class Meta:
        # `position` is the event's own first-come-first-served queue —
        # see events.views.event_signup, which assigns it sequentially and
        # uses it to decide who's confirmed vs waitlisted.
        ordering = ["position"]
        unique_together = [("event", "participant")]


class Award(models.Model):
    """Base award — shared name/description/icon. Every real award is one
    of the two subclasses below (multi-table inheritance, same pattern as
    accounts.User's DojoOwner/HelperAccount):
    MilestoneAward, unlocked by reaching a repeat-count threshold (e.g.
    the attendance wristbands), or BadgeAward, a one-off with no counter
    — you either did the specific thing or you haven't."""

    name = models.CharField(max_length=200)
    description = models.CharField(max_length=300, blank=True, default="")
    icon = models.ImageField(upload_to="awards/", null=True, blank=True)

    def __str__(self):
        return self.name


class MilestoneAward(Award):
    """Needs an unlock counter — e.g. the attendance wristbands (white at
    1 visit, green at 5, red at 10, black at 15). ParticipantAward's
    progress_current/progress_total track one participant's count toward
    this award's threshold."""

    threshold = models.PositiveIntegerField(
        help_text='How many times something must happen to unlock this — e.g. 5 for "attend 5 sessions".'
    )

    def __str__(self):
        return f"{self.name} ({self.threshold})"


class BadgeAward(Award):
    """No counter needed — a one-off you either have or don't (attended a
    specific event, submitted to a specific challenge)."""

    criteria = models.CharField(
        max_length=200, blank=True, default="", help_text='e.g. "Attended a CoderDojo for Girls session."'
    )


class ParticipantAward(models.Model):
    participant = models.ForeignKey("accounts.Participant", on_delete=models.CASCADE, related_name="awards")
    award = models.ForeignKey(Award, on_delete=models.CASCADE, related_name="participant_awards")

    earned_date = models.DateField(null=True, blank=True, help_text="Blank if still in progress.")
    progress_current = models.PositiveIntegerField(null=True, blank=True)
    progress_total = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = [("participant", "award")]

    def __str__(self):
        return f"{self.participant} - {self.award}"
