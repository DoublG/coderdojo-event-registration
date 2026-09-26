"""The dojo admin area's API page (/dojos/<id>/manage/api/, shell
dojos/_admin_base.html): the dojo's API clients, for its champion only
(dojos.access.MANAGE_API): add, new secret, delete. Making a client or
renewing its secret shows the
secret on the page once; a refresh doesn't show it again."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from dojos.access import MANAGE_API, require_dojo_access
from dojos.views import _admin_context

from . import services
from .models import DojoApiClient


def _page(request, access, **extra):
    clients = list(DojoApiClient.objects.filter(dojo=access.dojo).select_related("application", "created_by"))
    for client in clients:
        client.last_used = services.last_used(client)
    return render(
        request,
        "api/dojo_api_clients.html",
        {
            "clients": clients,
            "scope_choices": DojoApiClient.SCOPE_CHOICES,
            # The site's public address, as in mails: behind the proxy the
            # request itself looks like plain http.
            "token_url": settings.SITE_URL + reverse("oauth2_token"),
            "api_url": settings.SITE_URL + reverse("api-v1:api-root"),
            "docs_url": settings.SITE_URL + reverse("api-v1:openapi-view"),
            "active": "api",
            **_admin_context(request, access),
            **extra,
        },
    )


@login_required
def dojo_api_clients(request, dojo_id):
    access = require_dojo_access(request, dojo_id, MANAGE_API)
    if request.method == "POST":
        try:
            client, client_id, secret = services.create_client(
                access.dojo,
                request.POST.get("name"),
                request.POST.getlist("scope"),
                request.user,
            )
        except services.ApiClientError as error:
            return _page(request, access, error=str(error), name=request.POST.get("name", ""))
        return _page(request, access, new_client=client, new_client_id=client_id, new_secret=secret)
    return _page(request, access)


@login_required
def dojo_api_client_renew(request, dojo_id, client_id):
    access = require_dojo_access(request, dojo_id, MANAGE_API)
    client = get_object_or_404(DojoApiClient, id=client_id, dojo=access.dojo)
    if request.method != "POST":
        return redirect("dojo_api_clients", dojo_id=access.dojo.id)
    secret = services.renew_secret(client)
    return _page(request, access, new_client=client, new_client_id=client.application.client_id, new_secret=secret)


@login_required
def dojo_api_client_delete(request, dojo_id, client_id):
    """Delete a client (POST only): it stops at once and leaves the list."""
    access = require_dojo_access(request, dojo_id, MANAGE_API)
    client = get_object_or_404(DojoApiClient, id=client_id, dojo=access.dojo)
    if request.method == "POST":
        services.delete_client(client)
        messages.success(request, _("%(name)s is deleted: it can't use the API any more.") % {"name": client.name})
    return redirect("dojo_api_clients", dojo_id=access.dojo.id)
