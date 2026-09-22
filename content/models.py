from django.db import models


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

    class Meta:
        ordering = ["order"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class Announcement(models.Model):
    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE, related_name="announcements")
    date = models.DateField()
    text = models.TextField()

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.dojo} - {self.date}"
