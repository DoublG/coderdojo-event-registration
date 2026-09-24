from django.db import models
from django.db.models import Case, Q, When


class FAQQuerySet(models.QuerySet):
    def global_faqs(self):
        """Site-wide FAQs — not scoped to any Dojo, Event or Pathway (e.g.
        the homepage)."""
        return self.filter(dojo=None, event=None, pathway=None)

    def for_dojo(self, dojo):
        """A dojo's own FAQs plus the global ones, global first — so a
        dojo page always carries the site-wide answers (is it free? do
        parents need to stay?) alongside anything specific to that chapter,
        without duplicating the global questions onto every dojo."""
        return self.filter(Q(dojo=dojo) | Q(dojo=None, event=None, pathway=None)).order_by(
            Case(When(dojo=None, then=0), default=1), "order"
        )

    def for_event(self, event):
        """Same idea as for_dojo(), scoped to one session instead of one
        dojo: that event's own FAQs plus the global ones, global first."""
        return self.filter(Q(event=event) | Q(dojo=None, event=None, pathway=None)).order_by(
            Case(When(event=None, then=0), default=1), "order"
        )


class FAQ(models.Model):
    """A question/answer entry. Scoped to a Dojo, Event, or Pathway when
    one of those FKs is set; site-wide (e.g. shown on the homepage) when
    all three are blank."""

    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE, null=True, blank=True, related_name="faqs")
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, null=True, blank=True, related_name="faqs")
    pathway = models.ForeignKey(
        "pathways.Pathway", on_delete=models.CASCADE, null=True, blank=True, related_name="faqs"
    )

    question = models.CharField(max_length=300)
    answer = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)

    objects = FAQQuerySet.as_manager()

    class Meta:
        ordering = ["order"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class Testimonial(models.Model):
    """A quote from a parent, ninja or mentor. Scoped to a Dojo when set;
    site-wide (e.g. the homepage, which picks one at random) when blank."""

    dojo = models.ForeignKey(
        "dojos.Dojo", on_delete=models.CASCADE, null=True, blank=True, related_name="testimonials"
    )
    quote = models.TextField()
    author = models.CharField(max_length=200)
    role = models.CharField(max_length=200, blank=True, default="", help_text='e.g. "parent", "ninja (14)"')

    def __str__(self):
        return f"{self.author} — {self.quote[:40]}"


class AnnouncementManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("dojo__municipality")


class Announcement(models.Model):
    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE, related_name="announcements")
    date = models.DateField()
    text = models.TextField()

    objects = AnnouncementManager()

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.dojo} - {self.date}"


class OrganisationTeamMember(models.Model):
    """Someone listed on the organisation's team details page (the
    homepage's "Meet the team" and team/<id>/) — display only, with a
    position; "Member of the board" is just one possible position. Separate
    from access: being listed grants nothing, and not everyone with access
    to the management dashboards is listed. Maintained by staff; there's no
    self-service (DATA_MODEL.md §10)."""

    name = models.CharField(max_length=200)
    position = models.CharField(max_length=200, help_text='e.g. "Member of the board", "Volunteer coordinator"')
    email = models.EmailField(blank=True, default="", help_text="Shown on their detail page, if set.")
    bio = models.TextField(blank=True, default="")
    photo = models.ImageField(upload_to="team/", null=True, blank=True)
    focus_areas = models.CharField(
        max_length=300, blank=True, default="", help_text='Comma-separated, e.g. "Partnerships, Events"',
    )
    joined_date = models.DateField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0, help_text="Lower comes first.")
    is_public = models.BooleanField(default=True)
    account = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Optional: the person's own account, if they have one.",
    )

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.name} ({self.position})"

    # Shared avatar partial (dojos/partials/_mentor_avatar.html) colours the
    # ring by role; organisation team members all use the "board" ring.
    role = "board"

    @property
    def focus_area_list(self):
        return [area.strip() for area in self.focus_areas.split(",") if area.strip()]
