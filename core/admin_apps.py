from django.contrib.admin.apps import AdminConfig as DjangoAdminConfig


class AdminConfig(DjangoAdminConfig):
    """Django's admin, with core.admin_site.AdminSite as `admin.site` (in
    INSTALLED_APPS instead of django.contrib.admin)."""

    default_site = "core.admin_site.AdminSite"
