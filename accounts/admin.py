from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import DojoOwner, Guardianship, HelperAccount, Participant, User


class GuardianshipInline(admin.TabularInline):
    model = Guardianship
    fk_name = "guardian"
    extra = 0
    autocomplete_fields = ["ninja"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "first_name", "last_name", "account_type", "is_staff"]
    list_filter = ["account_type", "is_staff", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("CoderDojo", {"fields": ("account_type", "phone", "must_change_password",
                                  "background_check_required", "background_check_expires_at")}),
    )
    inlines = [GuardianshipInline]


class NinjaGuardianshipInline(admin.TabularInline):
    model = Guardianship
    fk_name = "ninja"
    extra = 0


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ["name", "date_of_birth", "home_dojo", "account"]
    search_fields = ["name"]
    inlines = [NinjaGuardianshipInline]


admin.site.register(DojoOwner, BaseUserAdmin)
admin.site.register(HelperAccount, BaseUserAdmin)
