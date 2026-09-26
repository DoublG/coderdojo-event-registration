from django.contrib import admin

from core.admin_translations import TranslationAdminMixin

from .models import FAQ, Announcement, OrganisationTeamMember, Promotion, Sponsor, Testimonial


@admin.register(Announcement)
class AnnouncementAdmin(TranslationAdminMixin, admin.ModelAdmin):
    """A dojo's "From this dojo" updates, with their texts in the dojo's other
    languages; normally posted on the dojo's Updates page."""


@admin.register(Promotion)
class PromotionAdmin(TranslationAdminMixin, admin.ModelAdmin):
    """Day-to-day, promotions are managed on the organisation dashboard
    (/manage/promotions/); this page is for fixing things by hand."""

    list_display = ["__str__", "event", "placement", "rank", "starts_at", "ends_at"]
    list_editable = ["rank"]
    list_filter = ["placement"]
    search_fields = ["title", "event__name"]
    raw_id_fields = ["event"]


@admin.register(OrganisationTeamMember)
class OrganisationTeamMemberAdmin(TranslationAdminMixin, admin.ModelAdmin):
    list_display = ["name", "position", "order", "is_public"]
    list_editable = ["order", "is_public"]
    search_fields = ["name", "position"]


@admin.register(FAQ, Testimonial)
class ScopedContentAdmin(TranslationAdminMixin, admin.ModelAdmin):
    """FAQs and testimonials, with their texts per language: the dojo's
    languages when scoped to a dojo (or its session), else the
    organisation's. Pick the dojo and save first; its other languages then
    get their own sections."""


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    """The homepage's "Made possible by" sponsors; managed day to day on the
    organisation dashboard's Sponsors page."""

    list_display = ["name", "url", "order", "is_public"]
    list_editable = ["order", "is_public"]
    search_fields = ["name"]

