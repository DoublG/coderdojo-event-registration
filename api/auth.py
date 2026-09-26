"""Who is calling the API: an access token from the OAuth 2.0 client
credentials flow (TOKEN_URL), of an active dojo API client, with the scope
the endpoint needs. No token, or an unknown or expired one (or one of a deleted client): 401. A
valid token without the scope: 403. `request.auth` is then the
`DojoApiClient`, and everything it does is limited to its own dojo.

The OpenAPI spec describes it as OAuth 2.0 too (django-ninja only has
plain bearer tokens and no scopes): one `OAuth2` security scheme with the
client credentials flow, its token URL and scopes, and on every endpoint
the scope it needs (`OAuth2.operation`), so OAuth-aware tools (the
reference page's Authorize button, client generators) get the token
themselves."""

from django.conf import settings
from ninja.errors import HttpError
from ninja.security.base import AuthBase
from ninja.throttling import AuthRateThrottle
from oauth2_provider.oauth2_backends import get_oauthlib_core

from .models import DojoApiClient

TOKEN_URL = "/api/oauth/token/"


class OAuth2(AuthBase):
    """ninja's security scheme name is the class name: "OAuth2"."""

    openapi_type = "oauth2"
    openapi_description = (
        "OAuth 2.0 client credentials: POST the client ID and secret your dojo's champion made to the token "
        "URL (grant_type=client_credentials, HTTP Basic or form fields), then send the access token as "
        "`Authorization: Bearer <token>`. A token lasts an hour. Revoke one at /api/oauth/revoke/."
    )
    openapi_flows = {
        "clientCredentials": {"tokenUrl": TOKEN_URL, "scopes": settings.OAUTH2_PROVIDER["SCOPES"]},
    }

    def __init__(self, scope):
        super().__init__()
        self.scope = scope

    def operation(self, **extra):
        """The decorator arguments of an endpoint that needs this scope: the
        check itself, the scope in the spec, and the error answers."""
        return {
            "auth": self,
            "openapi_extra": {"security": [{"OAuth2": [self.scope]}]},
            **extra,
        }

    def __call__(self, request):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return self.authenticate(request, token)

    def authenticate(self, request, token):
        valid, oauth_request = get_oauthlib_core().verify_request(request, scopes=[])
        if not valid:
            return None
        client = (
            DojoApiClient.objects.select_related("dojo", "account").filter(application=oauth_request.client).first()
        )
        if client is None:
            return None
        if not oauth_request.access_token.allow_scopes([self.scope]):
            raise HttpError(403, f"This client may not do this (needs the {self.scope} scope).")
        return client


class ClientRateThrottle(AuthRateThrottle):
    """Requests per client, whatever its name."""

    def get_cache_key(self, request):
        client = getattr(request, "auth", None)
        if client is None:
            return super().get_cache_key(request)
        return self.cache_format % {"scope": self.scope, "ident": f"client-{client.pk}"}
