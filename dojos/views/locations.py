"""The venues a dojo holds its sessions at (DojoLocation): the Locations page
in its admin area, `EDIT_SETTINGS`. The session form offers them (events.forms
.EventForm), copying the name and point onto the session."""

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from geo.geocoding import geocode

from ..access import EDIT_SETTINGS, require_dojo_access
from ..forms import DojoLocationForm
from .common import _admin_context


def _place(location):
    """Set `location.location` from its address; False when it couldn't be
    found (tolerant: a failed geocode never blocks the save)."""
    if not location.address:
        location.location = None
        return True
    try:
        coords = geocode(location.address)
    except requests.RequestException:
        coords = None
    if not coords:
        return False
    location.location = Point(coords[1], coords[0], srid=4326)
    return True


@login_required
def dojo_locations(request, dojo_id):
    """List the dojo's venues and add one."""
    access = require_dojo_access(request, dojo_id, EDIT_SETTINGS)
    dojo = access.dojo
    form = DojoLocationForm()
    if request.method == "POST":
        form = DojoLocationForm(request.POST)
        if form.is_valid():
            location = form.save(commit=False)
            location.dojo = dojo
            found = _place(location)
            location.save()
            messages.success(request, _("Location added."))
            if not found:
                messages.error(
                    request, _("We couldn't find that address on the map; the location is saved without it.")
                )
            return redirect("dojo_locations", dojo_id=dojo.id)
    return render(
        request,
        "dojos/dojo_locations.html",
        {"form": form, "locations": dojo.locations.all(), "active": "locations", **_admin_context(request, access)},
    )


@login_required
def dojo_location_delete(request, dojo_id, location_id):
    """Remove a venue (POST only). Sessions that used it keep their venue."""
    access = require_dojo_access(request, dojo_id, EDIT_SETTINGS)
    if request.method == "POST":
        get_object_or_404(access.dojo.locations, id=location_id).delete()
        messages.success(request, _("Location removed."))
    return redirect("dojo_locations", dojo_id=access.dojo.id)
