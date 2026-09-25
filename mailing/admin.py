from django.contrib import admin
from django.utils.html import format_html_join

from .models import (
    BounceRecord,
    Campaign,
    ConsentEvent,
    EmailMessage,
    EmailSuppression,
    EmailTemplate,
    MailPreference,
    Segment,
    SegmentGroup,
    SegmentRule,
)
from .preferences import subscribed_q
from .rendering import render
from .seed_templates import SAMPLE_CONTEXT
from .segmentation.resolver import SegmentResolver

AUDIENCE_SAMPLE_SIZE = 10


def _audience(segment, category=None):
    """Count and sample of a segment's accounts; with a mail `category`,
    only those who want that kind of mail (what a campaign would reach)."""
    if segment is None or segment.pk is None:
        return "—"
    recipients = SegmentResolver().resolve(segment)
    if category:
        recipients = recipients.filter(subscribed_q(category))
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

    @admin.display(description="Audience (active adults with an email who want this kind of mail)")
    def audience(self, obj):
        return _audience(obj.segment, obj.category)


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    """The mail queue and its history. Read-only: rows are created by
    mailing.services.send() and changed by the Celery tasks."""

    list_display = ["recipient", "category", "subject", "status", "attempts", "created_at", "sent_at"]
    list_filter = ["status", "category", "campaign"]
    search_fields = ["recipient", "subject", "message_id"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MailPreference)
class MailPreferenceAdmin(admin.ModelAdmin):
    """Read-only: preferences change through the account's own Mail
    preferences page or an unsubscribe link, which also log consent."""

    list_display = ["user", "category", "subscribed", "changed_at"]
    list_filter = ["category", "subscribed"]
    search_fields = ["user__email", "user__username"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ConsentEvent)
class ConsentEventAdmin(admin.ModelAdmin):
    """The append-only consent log."""

    list_display = ["created_at", "user", "category", "subscribed", "source", "wording_version"]
    list_filter = ["category", "source", "subscribed"]
    search_fields = ["user__email", "user__username"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BounceRecord)
class BounceRecordAdmin(admin.ModelAdmin):
    """What came back from the bounce mailbox (append-only)."""

    list_display = ["created_at", "email", "kind", "status_code", "diagnostic"]
    list_filter = ["kind"]
    search_fields = ["email", "diagnostic"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EmailSuppression)
class EmailSuppressionAdmin(admin.ModelAdmin):
    list_display = ["email", "reason", "note", "created_at"]
    list_filter = ["reason"]
    search_fields = ["email"]
