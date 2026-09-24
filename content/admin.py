from django.contrib import admin

from .models import FAQ, Announcement, OrganisationTeamMember, Testimonial

admin.site.register(FAQ)
admin.site.register(Announcement)
admin.site.register(Testimonial)


@admin.register(OrganisationTeamMember)
class OrganisationTeamMemberAdmin(admin.ModelAdmin):
    list_display = ["name", "position", "order", "is_public"]
    list_editable = ["order", "is_public"]
    search_fields = ["name", "position"]
