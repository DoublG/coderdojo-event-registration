from django.contrib import admin

from core.admin_translations import TranslationAdminMixin
from core.audit import AuditHistoryAdminMixin
from geo.widgets import BelgiumGISModelAdmin

from .models import Dojo, DojoMembership, DojoQuestion


class DojoMembershipInline(admin.TabularInline):
    """A dojo's team. Setting a dojo's champion happens here (an active
    membership with role champion) — there's no Dojo.owner any more."""

    model = DojoMembership
    fk_name = "dojo"
    extra = 0
    fields = ["user", "role", "status", "joined_at", "left_at"]
    autocomplete_fields = ["user"]


class DojoQuestionInline(admin.TabularInline):
    """The dojo's default sign-up questions (events.questions.copy_defaults).
    Their texts in the dojo's other languages are edited on the question's
    own admin page. Editing here bypasses the maximum."""

    model = DojoQuestion
    extra = 0
    fields = ["position", "text"]
    show_change_link = True


@admin.register(Dojo)
class DojoAdmin(TranslationAdminMixin, AuditHistoryAdminMixin, BelgiumGISModelAdmin):
    list_display = ["name", "kind", "status", "municipality"]
    list_filter = ["kind", "status"]
    search_fields = ["name"]
    inlines = [DojoMembershipInline, DojoQuestionInline]


@admin.register(DojoMembership)
class DojoMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "dojo", "role", "status", "joined_at"]
    list_filter = ["role", "status"]
    search_fields = ["user__username", "user__email", "dojo__name"]
    autocomplete_fields = ["user", "dojo"]


@admin.register(DojoQuestion)
class DojoQuestionAdmin(TranslationAdminMixin, admin.ModelAdmin):
    """A dojo's default sign-up question: new sessions start with a copy.
    The dojo team manages them on its Settings page (events.questions); an
    edit here bypasses the maximum."""

    list_display = ["text", "dojo", "position"]
    search_fields = ["text", "dojo__name"]
    raw_id_fields = ["dojo"]
