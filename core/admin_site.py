from django.contrib import admin


class AdminSite(admin.AdminSite):
    """`admin.site` (core.admin_apps.AdminConfig). The Django admin applies the
    organisation's sign-in policy too (accounts.sign_in): an account whose
    role needs two-step login gets in only with a verified session. Its login
    page is django-two-factor-auth's patch (TWO_FACTOR_PATCH_ADMIN), which
    sends everyone to the site's own login, so /admin/ can't skip two-step
    login either.

    Apart from superusers, it lets an account in only while it has asked for
    access and that access is still open (accounts.admin_access, DATA_MODEL.md
    §23): checked on every request, so access stops at the minute even when
    the job that takes staff status away runs late. The header says until
    when."""

    def has_permission(self, request):
        from accounts.admin_access import may_use_admin
        from accounts.sign_in import meets_requirement

        return super().has_permission(request) and may_use_admin(request.user) and meets_requirement(request)

    def each_context(self, request):
        from django.utils.translation import gettext as _

        from accounts.admin_access import open_grant, until_label

        context = super().each_context(request)
        grant = open_grant(request.user) if not request.user.is_superuser else None
        if grant is not None:
            context["site_header"] = _("%(header)s · access until %(until)s") % {
                "header": context["site_header"],
                "until": until_label(grant),
            }
        return context
