"""Saved reports (DATA_MODEL_REPORTS.md §30): an administrator's settings for
Perspective's viewer on one reporting dataset (reports.datasets). Only the
settings are stored, never the figures: they're worked out from the dataset
whenever the report is opened.

A published report shared with dojos shows in every dojo's admin area, to
its champion, read-only and on that dojo's own figures (reports.dojo_views).
A standard report comes with the site (reports.standard_reports, installed
by `manage.py load_standard_reports` on every deploy)."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ReportManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("created_by", "updated_by")


class Report(models.Model):
    DRAFT = "draft"
    PUBLISHED = "published"
    STATUS_CHOICES = [(DRAFT, _("Draft")), (PUBLISHED, _("Published"))]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    dataset = models.CharField(max_length=50, help_text="A key in reports.datasets.DATASETS.")
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="The viewer's settings, with columns as col:<key> and translated values as val:<key> "
        "(reports.config), so the report works in every language.",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=DRAFT,
        help_text="Only a published report is shown beyond the organisation's admins.",
    )
    shared_with_dojos = models.BooleanField(
        default=False,
        help_text="Published and shared: every dojo's champion sees it, on their own dojo's figures. Only for a "
        "dataset with a dojo column.",
    )
    position = models.PositiveIntegerField(default=0, help_text="Lowest first on the dojos' Reports page.")
    standard_key = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        help_text="A standard report that comes with the site (reports.standard_reports).",
    )
    standard_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="A fingerprint of the standard report as installed: while the row still matches it, "
        "load_standard_reports updates it with the code's newer version; once someone edits it, it's theirs.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ReportManager()

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name

    @property
    def is_shared(self):
        return self.status == self.PUBLISHED and self.shared_with_dojos

    def standard(self):
        """The code's definition of a standard report that's still as
        installed, else None."""
        from .standard_reports import STANDARD_REPORTS, fingerprint

        definition = STANDARD_REPORTS.get(self.standard_key or "")
        if definition is None or fingerprint(self) != self.standard_hash:
            return None
        return definition

    def label(self):
        """The name to show: a standard report still as installed in the
        reader's language, any other as written."""
        definition = self.standard()
        return str(definition.name) if definition else self.name

    def label_description(self):
        definition = self.standard()
        return str(definition.description) if definition else self.description
