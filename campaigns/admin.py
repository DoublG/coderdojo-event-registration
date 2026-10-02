from django.contrib import admin
from django.utils.html import format_html_join

from campaigns.models import Campaign, Journey, JourneyDelivery, Segment, SegmentGroup, SegmentRule
from campaigns.segmentation.resolver import SegmentResolver
from mailing.preferences import subscribed_q


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


@admin.register(Journey)
class JourneyAdmin(admin.ModelAdmin):
    """Run day to day from the organisation dashboard (/manage/journeys/)."""

    list_display = ["name", "segment", "template_key", "is_active", "cooldown_days"]
    list_filter = ["is_active"]


@admin.register(JourneyDelivery)
class JourneyDeliveryAdmin(admin.ModelAdmin):
    """Who got which journey when: what the cool-down is checked against."""

    list_display = ["created_at", "journey", "user", "email"]
    list_filter = ["journey"]
    search_fields = ["user__email"]


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
