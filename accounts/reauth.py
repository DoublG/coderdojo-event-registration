"""Confirming it's you without a password (DATA_MODEL.md §24).

A change that can't be taken back, or that weakens the login, asks for the
password first (accounts.forms.ConfirmIdentityForm). An account that logs
in with a link has none: for it, a login in the last RECENT_MINUTES is the
confirmation, and otherwise it asks for a login link that brings it back
to the page (accounts.views.login_link_reauth). Every login records its time
in the session here, whatever the way in.
"""

import time
from typing import Any

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.http import HttpRequest

LOGIN_AT_SESSION = "accounts_login_at"
RECENT_MINUTES = 10


@receiver(user_logged_in, dispatch_uid="accounts.reauth.record_login_time")
def _record_login_time(sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any) -> None:
    session = getattr(request, "session", None)
    if session is not None:
        session[LOGIN_AT_SESSION] = int(time.time())


def recently_authenticated(request: HttpRequest) -> bool:
    """Whether this session logged in within the last RECENT_MINUTES."""
    session = getattr(request, "session", None)
    login_at = session.get(LOGIN_AT_SESSION) if session is not None else None
    if not login_at:
        return False
    return time.time() - login_at <= RECENT_MINUTES * 60
