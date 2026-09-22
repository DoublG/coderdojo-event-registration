from django.contrib import admin

from .models import DojoApplication, MentorApplication

admin.site.register(DojoApplication)
admin.site.register(MentorApplication)
