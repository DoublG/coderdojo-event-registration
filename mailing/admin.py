from django.contrib import admin
from django.utils.html import format_html_join

from .models import Campaign, EmailMessage, EmailTemplate, Segment, SegmentGroup, SegmentRule
from .rendering import render
from .seed_templates import SAMPLE_CONTEXT
from .segmentation.resolver import SegmentResolver

AUDIENCE_SAMPLE_SIZE = 10


def _audience(segment):
    if segment is None or segment.pk is None:
        return "—"
    recipients = SegmentResolver().resolve(segment)
    sample = recipients.order_by("id")[:AUDIENCE_SAMPLE_SIZE]
    return format_html_join(
        "", "{}<br>", [(f"{recipients.count()} recipient(s)",)] + [(f"· {user.email}",) for user in sample]
    )


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ["key", "language", "category", "subject"]
    list_filter = ["category", "language"]
    search_fields = ["key", "subject", "body"]
    readonly_fields = ["preview"]

    @admin.display(description="Preview with example data")
    def preview(self, obj):
        if obj.pk is None or obj.key not in SAMPLE_CONTEXT:
            return "—"
        subject, body = render(obj.key, obj.language, SAMPLE_CONTEXT[obj.key])
        return format_html_join("", "<pre style='white-space: pre-wrap'>{}</pre>", [(f"{subject}\n\n{body}",)])


class SegmentGroupInline(admin.TabularInline):
    model = SegmentGroup
    extra = 0
    show_change_link = True
    fk_name = "segment"


@admin.register(Segment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "updated_at"]
    readonly_fields = ["audience"]
    inlines = [SegmentGroupInline]

    @admin.display(description="Audience (active adults with an email)")
    def audience(self, obj):
        return _audience(obj)


class SegmentRuleInline(admin.TabularInline):
    model = SegmentRule
    extra = 1


@admin.register(SegmentGroup)
class SegmentGroupAdmin(admin.ModelAdmin):
    list_display = ["__str__", "parent"]
    list_filter = ["segment"]
    inlines = [SegmentRuleInline]


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "template_key", "segment", "status", "scheduled_at"]
    list_filter = ["status", "category"]
    readonly_fields = ["audience", "segment_snapshot"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("segment")

    @admin.display(description="Audience (active adults with an email)")
    def audience(self, obj):
        return _audience(obj.segment)


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ["recipient", "type", "subject", "status", "created_at", "sent_at"]
    list_filter = ["status", "type"]
    search_fields = ["recipient", "subject"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
