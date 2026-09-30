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

    def login(self, request, extra_context=None):
        """Someone not logged in goes to the site's own login (the patch, through
        super()). Someone logged in without access would loop between that login
        (which sends a logged-in account on to `next`) and here, so they go to
        where they can ask for access (an organisation role), or get a 403."""
        if request.user.is_authenticated and not self.has_permission(request):
            from django.core.exceptions import PermissionDenied
            from django.shortcuts import redirect

            from accounts.admin_access import may_ask

            if may_ask(request.user):
                return redirect("manage_admin_access")
            raise PermissionDenied
        return super().login(request, extra_context)

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
