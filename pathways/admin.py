from django.contrib import admin

from .models import Pathway, PathwayProject, PathwayStep, Skill

admin.site.register(Pathway)
admin.site.register(PathwayStep)
admin.site.register(PathwayProject)
admin.site.register(Skill)
