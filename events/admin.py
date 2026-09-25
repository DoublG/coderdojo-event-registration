from django.contrib import admin

from geo.widgets import BelgiumGISModelAdmin

from .models import Badge, Belt, Event, NinjaBadge, NinjaBelt, NinjaEngagement, Registration, RegistrationCancellation


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


@admin.register(NinjaEngagement)
class NinjaEngagementAdmin(admin.ModelAdmin):
    """The nightly engagement snapshot (events.engagement). Rebuilt every
    night, so an edit here only lasts until the next rebuild."""

    list_display = ["ninja", "dojo", "stage", "attended_180d", "offered_180d", "missed_in_a_row", "last_attended"]
    list_filter = ["stage", "computed_on"]
    search_fields = ["ninja__name"]


@admin.register(RegistrationCancellation)
class RegistrationCancellationAdmin(admin.ModelAdmin):
    """The cancellation log (append-only in normal use: accounts.views.cancel_registration)."""

    list_display = ["cancelled_at", "ninja", "event", "was_waitlisted", "cancelled_by"]
    list_filter = ["was_waitlisted"]
    search_fields = ["ninja__name", "event__name"]
