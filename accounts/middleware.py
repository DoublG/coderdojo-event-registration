from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Intercepts every request from a logged-in user who still has a
    temporary, admin-issued password (DojoOwner/HelperAccount accounts
    created via the application-approval flow — see applications.admin)
    and redirects them to set a real one before they can reach anything
    else on the site.

    Compares against request.path rather than request.resolver_match:
    this runs before the view is resolved, so resolver_match isn't set
    on the request yet. Must sit after AuthenticationMiddleware in
    settings.MIDDLEWARE, since it relies on request.user."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _exempt_paths(self):
        return {reverse("change_password"), reverse("logout")}

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and user.must_change_password
            and not request.path.startswith(settings.STATIC_URL)
            and not request.path.startswith(settings.MEDIA_URL)
            and request.path not in self._exempt_paths()
        ):
            return redirect(reverse("change_password"))
        return self.get_response(request)
