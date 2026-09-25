from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Guardianship, Ninja, OrganisationRole, User


class GuardianshipInline(admin.TabularInline):
    model = Guardianship
    fk_name = "guardian"
    extra = 0
    autocomplete_fields = ["ninja"]


class OrganisationRoleInline(admin.TabularInline):
    """Granting/revoking here updates the account's staff status and groups
    (accounts.organisation) — don't set those by hand for these roles."""

    model = OrganisationRole
    extra = 0
    readonly_fields = ["granted_at"]


@admin.register(OrganisationRole)
class OrganisationRoleAdmin(admin.ModelAdmin):
    list_display = ["account", "role", "granted_at"]
    list_filter = ["role"]
    autocomplete_fields = ["account"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "first_name", "last_name", "account_type", "is_staff"]
    list_filter = ["account_type", "is_staff", "is_active", "preferred_language"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("CoderDojo", {"fields": ("account_type", "phone", "preferred_language", "postal_code", "must_change_password")}),
        ("Team-page profile", {"fields": ("display_name", "title", "bio", "photo", "show_on_team_pages")}),
    )
    search_fields = ["username", "email", "first_name", "last_name"]
    inlines = [GuardianshipInline, OrganisationRoleInline]


class NinjaGuardianshipInline(admin.TabularInline):
    model = Guardianship
    fk_name = "ninja"
    extra = 0


@admin.register(Ninja)
class NinjaAdmin(admin.ModelAdmin):
    list_display = ["name", "date_of_birth", "gender", "home_dojo", "current_belt", "account"]
    list_filter = ["gender"]
    search_fields = ["name"]
    inlines = [NinjaGuardianshipInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("belts__belt")

    @admin.display(description="Current belt")
    def current_belt(self, obj):
        return obj.current_belt or "—"
