from django.contrib import admin


class AdminSite(admin.AdminSite):
    """`admin.site` (core.admin_apps.AdminConfig). The Django admin applies the
    organisation's sign-in policy too (accounts.sign_in): an account whose
    role needs two-step login gets in only with a verified session. Its login
    page is django-two-factor-auth's patch (TWO_FACTOR_PATCH_ADMIN), which
    sends everyone to the site's own login, so /admin/ can't skip two-step
    login either."""

    def has_permission(self, request):
        from accounts.sign_in import meets_requirement

        return super().has_permission(request) and meets_requirement(request)
