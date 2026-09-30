"""Where passkeys are registered and checked (TWO_FACTOR_WEBAUTHN_ENTITIES_FORM_MIXIN).

django-two-factor-auth takes the relying party's id and origin from the
request, but behind nginx (and Level27's proxy) the request looks like plain
http, so a passkey signed for https://… would never match. SITE_URL is the
address people actually use, so both come from there."""

from hashlib import sha1
from urllib.parse import urlsplit

from django.conf import settings
from webauthn.helpers.structs import PublicKeyCredentialRpEntity, PublicKeyCredentialUserEntity


class SiteWebauthnEntitiesMixin:
    @property
    def webauthn_user(self):
        user = self.request.user
        return PublicKeyCredentialUserEntity(
            # Same id as the package's default: a hash of the pk, never the pk itself.
            # sha1 only makes an opaque id here, it protects nothing.
            id=sha1(str(user.pk).encode("utf-8")).hexdigest().encode("utf-8"),  # noqa: S324
            name=user.email or user.get_username(),
            display_name=user.get_full_name() or user.get_username(),
        )

    @property
    def webauthn_rp(self):
        return PublicKeyCredentialRpEntity(
            id=settings.TWO_FACTOR_WEBAUTHN_RP_ID or urlsplit(settings.SITE_URL).hostname,
            name=settings.TWO_FACTOR_WEBAUTHN_RP_NAME,
        )

    @property
    def webauthn_origin(self):
        parts = urlsplit(settings.SITE_URL)
        return f"{parts.scheme}://{parts.netloc}"
