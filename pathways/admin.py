from django.contrib import admin

from core.admin_translations import TranslationAdminMixin

from .models import Pathway, PathwayProject, PathwayStep, Skill


@admin.register(Pathway, PathwayStep, PathwayProject, Skill)
class OrganisationContentAdmin(TranslationAdminMixin, admin.ModelAdmin):
    """The organisation's pathway catalogue, with its texts per language
    (core.content_languages, settings.ORGANISATION_LANGUAGES)."""
