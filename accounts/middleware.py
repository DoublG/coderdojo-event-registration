from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Intercepts every request from a logged-in user whose account is
    flagged must_change_password (e.g. by an admin after resetting it) and
    redirects them to set a new password before they can reach anything
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


class SignInRequirementMiddleware:
    """Guides an account whose role needs a stronger login than it has
    (the organisation's sign-in policy, accounts.sign_in): without the device
    its role needs, every page sends it to its Sign-in security page to set
    one up; with the device but a session that didn't use it (logged in
    before the rule started), it's logged out and logs in again with its
    second step. The real lock is in the access helpers (see accounts.sign_in);
    this only makes sure people aren't left at a 404.

    Only the login pages, the Sign-in security pages and what they need
    (logout, the language switch, the JavaScript catalog, static and media
    files) stay open. htmx requests get an HX-Redirect instead of a
    redirect, so the whole page moves rather than a fragment."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _exempt(self, path):
        prefixes = (
            reverse("account_security"),
            reverse("login"),
            reverse("logout"),
            reverse("change_password"),
            reverse("set_language"),
            reverse("javascript-catalog"),
            settings.STATIC_URL,
            settings.MEDIA_URL,
        )
        return any(path.startswith(prefix) for prefix in prefixes)

    def __call__(self, request):
        from django.contrib import messages
        from django.contrib.auth import logout
        from django.http import HttpResponse
        from django.utils.http import urlencode
        from django.utils.translation import gettext as _

        from .sign_in import NEEDS_SETUP, NEEDS_VERIFY, request_status

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or self._exempt(request.path):
            return self.get_response(request)
        status = request_status(request)
        if status == NEEDS_SETUP:
            target = reverse("account_security")
        elif status == NEEDS_VERIFY:
            logout(request)
            messages.info(request, _("Your role needs two-step login. Please log in again with your second step."))
            target = f"{reverse('login')}?{urlencode({'next': request.get_full_path()})}"
        else:
            return self.get_response(request)
        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = target
            return response
        return redirect(target)
