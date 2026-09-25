from django.contrib import admin

from geo.widgets import BelgiumGISModelAdmin

from .models import Dojo, DojoMembership


class DojoMembershipInline(admin.TabularInline):
    """A dojo's team. Setting a dojo's champion happens here (an active
    membership with role champion) — there's no Dojo.owner any more."""

    model = DojoMembership
    fk_name = "dojo"
    extra = 0
    fields = ["user", "role", "status", "joined_at", "left_at"]
    autocomplete_fields = ["user"]


@admin.register(Dojo)
class DojoAdmin(BelgiumGISModelAdmin):
    list_display = ["name", "kind", "status", "municipality"]
    list_filter = ["kind", "status"]
    search_fields = ["name"]
    inlines = [DojoMembershipInline]


@admin.register(DojoMembership)
class DojoMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "dojo", "role", "status", "joined_at"]
    list_filter = ["role", "status"]
    search_fields = ["user__username", "user__email", "dojo__name"]
    autocomplete_fields = ["user", "dojo"]
