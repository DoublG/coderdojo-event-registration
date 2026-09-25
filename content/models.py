from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, Q, When
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.content_languages import OrganisationContent, ScopedContent, TranslatableModel


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


class FAQ(ScopedContent):
    """A question/answer entry. Scoped to a Dojo, Event, or Pathway when
    one of those FKs is set; site-wide (e.g. shown on the homepage) when
    all three are blank. In the dojo's languages when scoped to a dojo or
    its session, else in the organisation's."""

    TRANSLATABLE_FIELDS = ("question", "answer")

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


class Testimonial(ScopedContent):
    TRANSLATABLE_FIELDS = ("quote", "role")

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


class Announcement(TranslatableModel):
    TRANSLATABLE_FIELDS = ("text",)

    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE, related_name="announcements")
    date = models.DateField()
    text = models.TextField()

    objects = AnnouncementManager()

    def content_languages(self):
        return self.dojo.content_languages()

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.dojo} - {self.date}"


class OrganisationTeamMember(OrganisationContent):
    """Someone listed on the organisation's team details page (the
    homepage's "Meet the team" and team/<id>/) — display only, with a
    position; "Member of the board" is just one possible position. Separate
    from access: being listed grants nothing, and not everyone with access
    to the management dashboards is listed. Maintained by staff; there's no
    self-service (DATA_MODEL.md §10)."""

    TRANSLATABLE_FIELDS = ("position", "bio", "focus_areas")

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
        """In the page's language (core.content_languages)."""
        return [area.strip() for area in self.localized("focus_areas").split(",") if area.strip()]


def _clear_upcoming_cache():
    from django.core.cache import cache

    from events.search import CACHE_KEY

    cache.delete(CACHE_KEY)


class PromotionQuerySet(models.QuerySet):
    def showing(self, placement, now=None):
        """What a placement shows right now, `rank` first: started, not yet
        ended (at `ends_at`, or when the event starts if that's empty), and
        only for an event the public site shows (Event.objects.visible())
        that hasn't finished."""
        from events.models import Event

        now = now or timezone.now()
        return (
            self.filter(placement=placement, starts_at__lte=now, event__end_time__gt=now)
            .filter(Q(ends_at__gt=now) | Q(ends_at=None, event__start_time__gt=now))
            .filter(event__in=Event.objects.visible())
            .order_by("rank", "starts_at", "id")
        )


class PromotionManager(models.Manager.from_queryset(PromotionQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related("event__dojo__municipality")


class Promotion(OrganisationContent):
    """An event featured somewhere on the public site, for a while
    (DATA_MODEL.md §12). Separate from the event, so it can be switched on
    and off, ordered and pointed at different places without editing the
    event. Managed by the organisation's admin role (/manage/promotions/)."""

    TRANSLATABLE_FIELDS = ("title", "text")

    HOMEPAGE_HERO = "homepage_hero"
    EVENT_LIST_TOP = "event_list_top"
    UPCOMING_FIRST = "upcoming_first"
    DOJO_FINDER_BANNER = "dojo_finder_banner"
    PLACEMENT_CHOICES = [
        (HOMEPAGE_HERO, _("Homepage: large card under the introduction")),
        (EVENT_LIST_TOP, _("Events page: pinned above the list")),
        (UPCOMING_FIRST, _("Homepage: first in Upcoming sessions")),
        (DOJO_FINDER_BANNER, _("Dojo finder: banner above the results")),
    ]

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="promotions")
    placement = models.CharField(max_length=20, choices=PLACEMENT_CHOICES)
    rank = models.PositiveSmallIntegerField(default=0, help_text="Lower shows first within a placement.")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(
        null=True, blank=True, help_text="Empty: the promotion ends when the event starts.",
    )
    title = models.CharField(max_length=200, blank=True, default="", help_text="Optional: replaces the event's name.")
    image = models.ImageField(
        upload_to="promotions/", null=True, blank=True, help_text="Optional: replaces the event's banner.",
    )
    text = models.CharField(max_length=300, blank=True, default="", help_text="Optional short pitch.")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PromotionManager()

    class Meta:
        ordering = ["placement", "rank", "starts_at"]

    def __str__(self):
        return f"{self.display_title} ({self.get_placement_display()})"

    # The upcoming-sessions carousel caches its list, `upcoming_first` order
    # included (events.search): a change shows at once, not a minute later.
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        _clear_upcoming_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        _clear_upcoming_cache()
        return result

    def clean(self):
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "The end must be after the start."})

    @property
    def display_title(self):
        return self.localized("title") or self.event.localized("name")

    @property
    def display_image(self):
        return self.image or self.event.image

    @property
    def effective_end(self):
        return self.ends_at or self.event.start_time

    def is_showing(self, now=None):
        now = now or timezone.now()
        return self.starts_at <= now < self.effective_end and now < self.event.end_time
