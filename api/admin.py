from django.contrib import admin

from .models import DojoApiClient


@admin.register(DojoApiClient)
class DojoApiClientAdmin(admin.ModelAdmin):
    """A dojo's API clients (api.services). Normally made, renewed and
    deleted by the dojo's champion on the dojo's API page; an edit here
    bypasses that (a new secret is set on the OAuth application itself,
    under Django OAuth Toolkit)."""

    list_display = ["name", "dojo", "scopes", "account", "created_by", "created_at"]
    search_fields = ["name", "dojo__name"]
    raw_id_fields = ["dojo", "application", "account", "created_by"]
