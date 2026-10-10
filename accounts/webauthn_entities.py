"""Where passkeys are registered and checked (TWO_FACTOR_WEBAUTHN_ENTITIES_FORM_MIXIN).

django-two-factor-auth takes the relying party's id and origin from the
request, but behind nginx (and Level27's proxy) the request looks like plain
http, so a passkey signed for https://… would never match. SITE_URL is the
address people actually use, so both come from there."""

from hashlib import sha1
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from webauthn.helpers.structs import PublicKeyCredentialRpEntity, PublicKeyCredentialUserEntity


class SiteWebauthnEntitiesMixin:
    request: HttpRequest  # set by the view this is mixed into

    @property
    def webauthn_user(self) -> PublicKeyCredentialUserEntity:
        user = self.request.user
        if not user.is_authenticated:  # the package only sets passkeys up for a logged-in account
            raise PermissionDenied
        return PublicKeyCredentialUserEntity(
            # Same id as the package's default: a hash of the pk, never the pk itself.
            # sha1 only makes an opaque id here, it protects nothing.
            id=sha1(str(user.pk).encode("utf-8")).hexdigest().encode("utf-8"),  # noqa: S324
            name=user.email or user.get_username(),
            display_name=user.get_full_name() or user.get_username(),
        )

    @property
    def webauthn_rp(self) -> PublicKeyCredentialRpEntity:
        return PublicKeyCredentialRpEntity(
            # The package's AppConfig defaults it to None.
            id=getattr(settings, "TWO_FACTOR_WEBAUTHN_RP_ID", None) or urlsplit(settings.SITE_URL).hostname,
            name=settings.TWO_FACTOR_WEBAUTHN_RP_NAME,
        )

    @property
    def webauthn_origin(self) -> str:
        parts = urlsplit(settings.SITE_URL)
        return f"{parts.scheme}://{parts.netloc}"
