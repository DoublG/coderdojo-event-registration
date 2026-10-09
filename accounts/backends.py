from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from django.http import HttpRequest

if TYPE_CHECKING:
    from .models import User


class EmailOrUsernameBackend(ModelBackend):
    """Authenticates against either username or email — the login form
    asks for "Email" (matching the site's copy), but seeded demo accounts
    are keyed by username, so this accepts whichever the user has."""

    def authenticate(
        self, request: HttpRequest | None, username: str | None = None, password: str | None = None, **kwargs: Any
    ) -> "User | None":
        if username is None or password is None:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
