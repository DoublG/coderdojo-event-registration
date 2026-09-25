from django.contrib import admin

from geo.widgets import BelgiumGISModelAdmin

from .models import Badge, Belt, Event, NinjaBadge, NinjaBelt, Registration


@admin.register(Event)
class EventAdmin(BelgiumGISModelAdmin):
    list_display = ["name", "dojo", "start_time", "status", "audience"]
    list_filter = ["status", "audience"]
    search_fields = ["name", "dojo__name"]
admin.site.register(Registration)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "threshold", "grants_belt"]
    list_filter = ["kind"]


@admin.register(Belt)
class BeltAdmin(admin.ModelAdmin):
    list_display = ["level", "name", "colour"]


@admin.register(NinjaBadge)
class NinjaBadgeAdmin(admin.ModelAdmin):
    list_display = ["ninja", "badge", "earned_date", "progress_current", "progress_total"]
    list_filter = ["badge"]


@admin.register(NinjaBelt)
class NinjaBeltAdmin(admin.ModelAdmin):
    """Append-only history in normal use: belts are awarded from the dojo's
    attendance list (events.awards), where the rules are enforced. Editable
    here only to fix a mistake by hand, which bypasses those rules."""

    list_display = ["ninja", "belt", "awarded_on", "awarded_by_label"]
    list_filter = ["belt"]
