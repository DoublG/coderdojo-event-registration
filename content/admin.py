from django.contrib import admin

from .models import FAQ, Announcement, Testimonial

admin.site.register(FAQ)
admin.site.register(Announcement)
admin.site.register(Testimonial)
