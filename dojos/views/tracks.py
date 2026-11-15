"""A session's workshops (events.EventTrack) in the dojo's admin area: the
Tracks card on the session's page. The rules are events.tracks. Plain
posts that go back to the card (`MANAGE_EVENTS`, scoped to the URL's event)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from events import tracks
from events.models import Event, EventTrack

from ..access import MANAGE_EVENTS, require_dojo_access


def tracks_context(event):
    """What the Tracks card needs: each track with its confirmed and waiting
    children, and whether another can be added."""
    if event.registers_externally:
        return {"tracks_shown": False}
    counts = tracks.counts(event)
    rows = []
    for track in event.tracks.all():
        row = counts.get(track.pk, {"confirmed": 0, "waiting": 0})
        rows.append({"track": track, **row, "removable": not (row["confirmed"] or row["waiting"])})
    return {
        "tracks_shown": True,
        "track_rows": rows,
        "can_add_track": len(rows) < tracks.max_tracks(),
        "max_tracks": tracks.max_tracks(),
    }


def _back(dojo_id, event_id):
    return redirect(reverse("dojo_event_detail", args=[dojo_id, event_id]) + "#tracks")


def _event(request, dojo_id, event_id):
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    return access, get_object_or_404(Event, id=event_id, dojo=access.dojo)


@login_required
@require_POST
def dojo_event_track_add(request, dojo_id, event_id):
    access, event = _event(request, dojo_id, event_id)
    try:
        tracks.add_track(event, request.POST.get("name", ""), request.POST.get("places", ""))
    except tracks.TrackError as problem:
        messages.error(request, str(problem))
    else:
        messages.success(request, _("Track added."))
    return _back(access.dojo.id, event.id)


@login_required
@require_POST
def dojo_event_track_edit(request, dojo_id, event_id, track_id):
    access, event = _event(request, dojo_id, event_id)
    track = get_object_or_404(EventTrack, id=track_id, event=event)
    try:
        tracks.edit_track(track, request.POST.get("name", ""), request.POST.get("places", ""))
    except tracks.TrackError as problem:
        messages.error(request, str(problem))
    else:
        messages.success(request, _("Track saved."))
    return _back(access.dojo.id, event.id)


@login_required
@require_POST
def dojo_event_track_remove(request, dojo_id, event_id, track_id):
    access, event = _event(request, dojo_id, event_id)
    track = get_object_or_404(EventTrack, id=track_id, event=event)
    try:
        tracks.remove_track(track)
    except tracks.TrackError as problem:
        messages.error(request, str(problem))
    else:
        messages.success(request, _("Track removed."))
    return _back(access.dojo.id, event.id)
