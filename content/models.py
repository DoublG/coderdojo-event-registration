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


class Announcement(models.Model):
    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE, related_name="announcements")
    date = models.DateField()
    text = models.TextField()

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.dojo} - {self.date}"
