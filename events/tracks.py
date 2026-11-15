"""The workshops (tracks) of a session (DATA_MODEL.md §4, "Tracks"): adding,
changing and removing them. A session with tracks has every child pick one;
a track's places and waiting list are counted apart from the others
(events.registrations), under the session's own total.

Raising a track's places gives the new places to the children waiting in
it (`registrations.fill_free_places`). Lowering them never takes a place
from a child who has one."""

from collections.abc import Mapping

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils.translation import gettext as _

from .models import Event, EventTrack

MAX_NAME_LENGTH = 100


class TrackError(Exception):
    """A change to a session's tracks that can't happen, with a message for
    the dojo team."""


def max_tracks() -> int:
    """At most this many tracks per session (settings.SESSION_TRACKS_MAX, 8 by default)."""
    return int(getattr(settings, "SESSION_TRACKS_MAX", 8))


def _clean(name: str, places: int | str | None) -> tuple[str, int]:
    name = (name or "").strip()
    if not name:
        raise TrackError(_("Write the track's name."))
    if len(name) > MAX_NAME_LENGTH:
        raise TrackError(_("Keep the name under %(max)s characters.") % {"max": MAX_NAME_LENGTH})
    try:
        count = int(places) if places not in (None, "") else 0
    except (TypeError, ValueError):
        count = 0
    if count < 1:
        raise TrackError(_("A track needs at least one place."))
    return name, count


def _check_event(event: Event) -> None:
    if event.registers_externally:
        raise TrackError(_("Families sign up for this session on another website, so it has no tracks here."))


def add_track(
    event: Event, name: str, places: int | str | None, translations: Mapping[str, str] | None = None
) -> EventTrack:
    """Add a track at the end of the session's list."""
    _check_event(event)
    name, count = _clean(name, places)
    with transaction.atomic():
        # Locks the session, so two team members adding at once can't go past the maximum.
        Event.objects.select_for_update().filter(pk=event.pk).first()
        existing = EventTrack.objects.filter(event=event)
        if existing.count() >= max_tracks():
            raise TrackError(_("At most %(max)s tracks: remove one first.") % {"max": max_tracks()})
        position = (existing.aggregate(Max("position"))["position__max"] or 0) + 1
        track = EventTrack(event=event, name=name, places=count, position=position)
        _set_translations(track, translations)
        track.save()
    return track


def edit_track(
    track: EventTrack, name: str, places: int | str | None, translations: Mapping[str, str] | None = None
) -> EventTrack:
    """Change a track's name and places; more places move the children
    waiting in it up (and mail their families)."""
    from . import registrations

    name, count = _clean(name, places)
    raised = count > track.places
    track.name, track.places = name, count
    _set_translations(track, translations)
    track.save()
    if raised:
        registrations.fill_free_places(track.event)
    return track


def _set_translations(track: EventTrack, translations: Mapping[str, str] | None) -> None:
    for language in track.content_languages()[1:]:
        if translations is not None and language in translations:
            track.set_translation(language, "name", (translations[language] or "").strip()[:MAX_NAME_LENGTH])


def remove_track(track: EventTrack) -> None:
    """Remove a track. Not while children are signed up in it (confirmed or
    waiting): their places would lose their workshop."""
    if track.registrations.exists():
        raise TrackError(_("Children are signed up for this track: it can't be removed."))
    track.delete()


def counts(event: Event) -> dict[int, dict[str, int]]:
    """{track id: {"confirmed": n, "waiting": n}} for the session's tracks."""
    rows = (
        EventTrack.objects.filter(event=event)
        .annotate(
            confirmed=Count("registrations", filter=Q(registrations__waiting_list=False)),
            waiting=Count("registrations", filter=Q(registrations__waiting_list=True)),
        )
        .values("pk", "confirmed", "waiting")
    )
    return {row["pk"]: {"confirmed": row["confirmed"], "waiting": row["waiting"]} for row in rows}
