"""django-oauth-toolkit's scopes backend (OAUTH2_PROVIDER["SCOPES_BACKEND_CLASS"]):
a client can only get the scopes its dojo's champion gave it."""

from oauth2_provider.scopes import SettingsScopes


class ClientScopes(SettingsScopes):
    def _client_scopes(self, application):
        client = getattr(application, "dojo_client", None) if application is not None else None
        if client is None:
            return []
        return [scope for scope in client.scopes if scope in self.get_all_scopes()]

    def get_available_scopes(self, application=None, request=None, *args, **kwargs):
        return self._client_scopes(application)

    def get_default_scopes(self, application=None, request=None, *args, **kwargs):
        return self._client_scopes(application)
