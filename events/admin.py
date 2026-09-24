from django.contrib import admin

from geo.widgets import BelgiumGISModelAdmin

from .models import Badge, Belt, Event, NinjaBadge, NinjaBelt, Registration

admin.site.register(Event, BelgiumGISModelAdmin)
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
    list_display = ["participant", "badge", "earned_date", "progress_current", "progress_total"]
    list_filter = ["badge"]


@admin.register(NinjaBelt)
class NinjaBeltAdmin(admin.ModelAdmin):
    """Append-only history: rows can be looked at (and removed by someone
    with delete rights, to undo a mistake), never edited. Belts are awarded
    from the dojo's attendance list, where the rules are enforced."""

    list_display = ["participant", "belt", "awarded_on", "awarded_by_label"]
    list_filter = ["belt"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
