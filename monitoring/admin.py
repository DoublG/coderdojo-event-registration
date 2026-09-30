from django.contrib import admin

from .models import CapacitySample


@admin.register(CapacitySample)
class CapacitySampleAdmin(admin.ModelAdmin):
    """The daily measurements (CAPACITY.md). Taken by the
    `record_capacity_sample` job; an edit here only changes the record."""

    list_display = ("taken_on", "taken_at")
    date_hierarchy = "taken_on"
