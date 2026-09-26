"""Making, renewing and deleting a dojo's API clients (DATA_MODEL.md §13).
The dojo's API page (api.views) only calls these; `ApiClientError` carries
a message for the champion. The client secret is returned once, when it's
made or renewed, and only its hash is kept."""

from django.db import transaction
from django.utils.text import slugify
from django.utils.translation import gettext as _
from oauth2_provider.generators import generate_client_secret
from oauth2_provider.models import get_access_token_model, get_application_model, get_refresh_token_model

from accounts.models import User
from accounts.provisioning import unique_username

from .models import DojoApiClient


class ApiClientError(Exception):
    """A user-facing reason the change can't be made."""


def _clean(name, scopes):
    name = (name or "").strip()
    if not name:
        raise ApiClientError(_("Give the client a name."))
    allowed = dict(DojoApiClient.SCOPE_CHOICES)
    scopes = [scope for scope in allowed if scope in set(scopes or [])]
    if not scopes:
        raise ApiClientError(_("Choose what the client may do."))
    return name[:100], scopes


@transaction.atomic
def create_client(dojo, name, scopes, by):
    """A new client for `dojo`. Returns (client, client_id, client_secret):
    the secret is shown once and never stored in the clear."""
    name, scopes = _clean(name, scopes)
    account = User(
        username=unique_username(f"api-{slugify(name) or 'client'}"),
        account_type=User.SERVICE,
        first_name=name,
    )
    account.set_unusable_password()
    account.save()
    secret = generate_client_secret()
    Application = get_application_model()
    application = Application.objects.create(
        name=f"{dojo.name}: {name}"[:255],
        user=account,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
        client_secret=secret,
        hash_client_secret=True,
        skip_authorization=True,
    )
    client = DojoApiClient.objects.create(
        dojo=dojo,
        name=name,
        scopes=scopes,
        application=application,
        account=account,
        created_by=by,
    )
    return client, application.client_id, secret


def _end_tokens(application):
    get_refresh_token_model().objects.filter(application=application).delete()
    get_access_token_model().objects.filter(application=application).delete()


@transaction.atomic
def renew_secret(client):
    """A new secret for the client; the old one and every token it got stop
    working. Returns the new secret, shown once."""
    secret = generate_client_secret()
    application = client.application
    application.client_secret = secret
    application.save()
    _end_tokens(application)
    return secret


@transaction.atomic
def delete_client(client):
    """The client stops at once and leaves the dojo's list: its tokens, its
    application and this row go. Its technical account stays, switched
    off, so what the client marked keeps its name (TeamAttendance.marked_by,
    the audit log)."""
    application = client.application
    account = client.account
    _end_tokens(application)
    client.delete()
    application.delete()
    if account.is_active:
        account.is_active = False
        account.save(update_fields=["is_active"])


def last_used(client):
    """When the client last got a token, or None."""
    token = get_access_token_model().objects.filter(application=client.application).order_by("-created").first()
    return token.created if token else None
