from django.contrib import admin

from .models import FAQ, Announcement, OrganisationTeamMember, Promotion, Testimonial

admin.site.register(FAQ)
admin.site.register(Announcement)
admin.site.register(Testimonial)


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    """Day-to-day, promotions are managed on the organisation dashboard
    (/manage/promotions/); this page is for fixing things by hand."""

    list_display = ["__str__", "event", "placement", "rank", "starts_at", "ends_at"]
    list_editable = ["rank"]
    list_filter = ["placement"]
    search_fields = ["title", "event__name"]
    raw_id_fields = ["event"]


@admin.register(OrganisationTeamMember)
class OrganisationTeamMemberAdmin(admin.ModelAdmin):
    list_display = ["name", "position", "order", "is_public"]
    list_editable = ["order", "is_public"]
    search_fields = ["name", "position"]
