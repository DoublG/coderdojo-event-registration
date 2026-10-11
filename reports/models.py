"""Saved reports (DATA_MODEL_REPORTS.md §30): an administrator's settings for
Perspective's viewer on one reporting dataset (reports.datasets). Only the
settings are stored, never the figures: they're worked out from the dataset
whenever the report is opened."""

from django.conf import settings
from django.db import models


class ReportManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("created_by", "updated_by")


class Report(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    dataset = models.CharField(max_length=50, help_text="A key in reports.datasets.DATASETS.")
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="The viewer's settings, with columns as col:<key> and translated values as val:<key> "
        "(reports.config), so the report works in every language.",
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
        ordering = ["name"]

    def __str__(self):
        return self.name
