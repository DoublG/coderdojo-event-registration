"""A dojo's own settings in its admin area: creating a dojo, the Settings page
(with the address geocoded), the lifecycle actions and the Updates page."""

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from applications.services import is_approved_champion
from core.content_languages import normalize
from geo.geocoding import find_province, geocode

from .. import team
from ..access import (
    EDIT_SETTINGS,
    MANAGE_LIFECYCLE,
    POST_UPDATES,
    require_dojo_access,
)
from ..forms import (
    AnnouncementForm,
    DojoCreateForm,
    DojoProfileForm,
)
from ..models import Dojo, DojoMembership
from .common import PUBLIC_UPDATES_LIMIT, _admin_context


def _geocode_address(dojo):
    """Set dojo.location (and province) from dojo.address. Tolerant: a failed
    or no-match geocode never blocks a save — returns False and leaves the
    location as it was (same pattern as dojos.search.resolve_search_origin)."""
    try:
        coords = geocode(dojo.address)
    except requests.RequestException:
        coords = None
    if not coords:
        return False
    lat, lon = coords
    dojo.location = Point(lon, lat, srid=4326)
    dojo.province = find_province(dojo.location)
    return True


@login_required
def dojo_create(request):
    """An approved champion creates a dojo (DATA_MODEL.md §10): it starts as
    a draft, hidden from the public site, with them as its champion. They
    fill in the rest on the Settings page and launch it from there."""
    if not is_approved_champion(request.user):
        messages.error(request, _("Only approved champions with a valid background check can create a dojo."))
        return redirect("account_home")

    if request.method == "POST":
        form = DojoCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                dojo = form.save(commit=False)
                dojo.status = Dojo.DRAFT
                # Starts in the champion's own language; changed on the Settings page.
                dojo.languages = [normalize(request.user.preferred_language or get_language()) or "nl-be"]
                dojo.created_by = request.user
                geocode_failed = bool(dojo.address) and not _geocode_address(dojo)
                dojo.save()
                DojoMembership.objects.create(
                    dojo=dojo,
                    user=request.user,
                    role=DojoMembership.CHAMPION,
                    status=DojoMembership.ACTIVE,
                    joined_at=timezone.now(),
                    requested_by=request.user,
                )
            messages.success(
                request,
                _("%(dojo)s has been created as a draft. Fill in its profile, then launch it.") % {"dojo": dojo.name},
            )
            if geocode_failed:
                messages.error(request, _("We couldn't find that address on the map; check it on this page."))
            return redirect("dojo_manage", dojo_id=dojo.id)
    else:
        form = DojoCreateForm()
    return render(request, "dojos/dojo_create.html", {"form": form})


@login_required
def dojo_manage(request, dojo_id):
    """Lets a dojo owner edit everything shown on their dojo's public
    profile (dojo_detail.html) — see DojoProfileForm for the exact field
    list. Address changes are re-geocoded on save (same tolerant-failure
    pattern as dojos.search.resolve_search_origin: a failed/no-match
    geocode never blocks the save, it just leaves location/province as
    they were), and a successful geocode also refreshes province via
    geo.geocoding.find_province so distance search and the map link stay
    accurate without the owner ever touching either field directly."""
    access = require_dojo_access(request, dojo_id, EDIT_SETTINGS)
    dojo = access.dojo
    saved = False
    geocode_failed = False

    if request.method == "POST":
        form = DojoProfileForm(request.POST, request.FILES, instance=dojo)
        if form.is_valid():
            address_changed = "address" in form.changed_data
            dojo = form.save(commit=False)

            if address_changed and dojo.address:
                geocode_failed = not _geocode_address(dojo)

            dojo.save()
            form.save_m2m()  # pathways — commit=False above skipped them
            saved = True
    else:
        form = DojoProfileForm(instance=dojo)

    return render(
        request,
        "dojos/dojo_manage.html",
        {
            "form": form,
            "saved": saved,
            "geocode_failed": geocode_failed,
            "active": "settings",
            "active_event_count": team.active_events(dojo).count(),
            **_admin_context(request, access),
        },
    )


@login_required
def dojo_set_lifecycle(request, dojo_id):
    """The champion's lifecycle buttons on the settings page (POST only):
    launch, go dormant, restart, archive, reopen — see dojos.team for the
    rules (no active events before dormant/archived, etc.)."""
    access = require_dojo_access(request, dojo_id, MANAGE_LIFECYCLE)
    if request.method == "POST":
        try:
            team.change_status(access.dojo, request.POST.get("action", ""))
            messages.success(
                request,
                _("%(dojo)s is now %(lower)s.")
                % {"dojo": access.dojo.name, "lower": access.dojo.get_status_display().lower()},
            )
        except team.TeamError as error:
            messages.error(request, str(error))
    return redirect("dojo_manage", dojo_id=access.dojo.id)


@login_required
def dojo_updates(request, dojo_id):
    """The admin sidebar's "Updates" page: the dojo's "From this dojo"
    updates (content.Announcement), newest first, and with POST_UPDATES a
    form to post a new one, dated today."""
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    form = AnnouncementForm(dojo=dojo)
    if request.method == "POST":
        if not access.can_post_updates:
            raise PermissionDenied
        form = AnnouncementForm(request.POST, dojo=dojo)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.dojo = dojo
            announcement.date = timezone.localdate()
            announcement.save()
            messages.success(request, _("Update posted on the dojo's page."))
            return redirect("dojo_updates", dojo_id=dojo.id)
    return render(
        request,
        "dojos/dojo_updates.html",
        {
            "form": form,
            "announcements": dojo.announcements.all(),
            "public_limit": PUBLIC_UPDATES_LIMIT,
            "active": "updates",
            **_admin_context(request, access),
        },
    )


@login_required
def dojo_update_delete(request, dojo_id, announcement_id):
    """Remove one update (POST only, POST_UPDATES)."""
    access = require_dojo_access(request, dojo_id, POST_UPDATES)
    if request.method == "POST":
        get_object_or_404(access.dojo.announcements, id=announcement_id).delete()
        messages.success(request, _("Update removed."))
    return redirect("dojo_updates", dojo_id=access.dojo.id)
