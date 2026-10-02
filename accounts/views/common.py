"""What the accounts app's pages share: finding one of the account's own children
(a 404 for anyone else's) and the page's language for a new account."""

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404

from ..models import Ninja

# Small on purpose — small enough that most children's award shelf
# actually spans more than one page, so the lazy-load carousel (same
# pattern as the homepage's "Upcoming sessions", see
# events.views.upcoming_sessions_widget) has something to demonstrate.
BADGES_PAGE_SIZE = 4


def _get_own_ninja(request, ninja_id, allow_self=False):
    """A ninja the logged-in account is a guardian of — or, with
    allow_self, the ninja's own login looking at their own page. 404s
    rather than 403s on a mismatch, so a guessed id doesn't even confirm
    another family's child exists."""
    ninja = get_object_or_404(Ninja, id=ninja_id)
    is_guardian = ninja.guardianships.filter(guardian=request.user).exists()
    is_self = allow_self and ninja.account_id == request.user.pk
    if not (is_guardian or is_self):
        raise Http404
    return ninja


def _site_language(request):
    """The LANGUAGES code of the language the page is shown in, as the
    default for a new account's mail language."""
    codes = [code for code, _name in settings.LANGUAGES]
    current = (getattr(request, "LANGUAGE_CODE", "") or "").lower()
    return next((code for code in codes if code == current), None) or next(
        (code for code in codes if code.split("-")[0] == current.split("-")[0]), codes[0]
    )
