from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Guardianship, OrganisationRole, Participant, User


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
    list_filter = ["account_type", "is_staff", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("CoderDojo", {"fields": ("account_type", "phone", "must_change_password")}),
        ("Team-page profile", {"fields": ("display_name", "title", "bio", "photo", "show_on_team_pages")}),
    )
    search_fields = ["username", "email", "first_name", "last_name"]
    inlines = [GuardianshipInline, OrganisationRoleInline]


class NinjaGuardianshipInline(admin.TabularInline):
    model = Guardianship
    fk_name = "ninja"
    extra = 0


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ["name", "date_of_birth", "home_dojo", "account"]
    search_fields = ["name"]
    inlines = [NinjaGuardianshipInline]
