"""Who gets a place when a session holds some for the dojo team's children
(DATA_MODEL.md §4, "Reserved places").

A session may hold `reserved_places` of its places for the children of the
dojo's team (an active champion or mentor among their guardians) until
`Event.reserved_released`; from then on they're ordinary places. A child of
the team can take any free place; any other child only one that isn't
still held. These rules are used under the session's lock
(events.registrations), never from a page's own count."""

from collections.abc import Iterable
from datetime import datetime

from django.utils import timezone

from accounts.models import Guardianship
from dojos.models import DojoMembership

from .models import Event, Registration


def team_child_ids(event: Event, ninja_ids: Iterable[int]) -> set[int]:
    """Which of these children have a guardian who is an active champion or
    mentor of the session's dojo."""
    return set(
        Guardianship.objects.filter(
            ninja_id__in=list(ninja_ids),
            guardian__dojo_memberships__dojo_id=event.dojo_id,
            guardian__dojo_memberships__status=DojoMembership.ACTIVE,
            guardian__dojo_memberships__role__in=DojoMembership.MANAGER_ROLES,
        ).values_list("ninja_id", flat=True)
    )


def team_confirmed(event: Event) -> int:
    """How many confirmed places are taken by children of the team."""
    confirmed = Registration.objects.filter(event=event, waiting_list=False).values_list("ninja_id", flat=True)
    return len(team_child_ids(event, confirmed))


def held_places(event: Event, team_taken: int, now: datetime | None = None) -> int:
    """The places still held for the team's children: the reserve minus what
    they took, nothing once it's released."""
    if event.reserved_places <= 0 or event.reserved_released(now):
        return 0
    return max(0, event.reserved_places - team_taken)


def can_take(
    event: Event, *, is_team_child: bool, confirmed: int, team_taken: int, now: datetime | None = None
) -> bool:
    """Whether one more child gets a confirmed place, given the places taken."""
    if confirmed >= event.places:
        return False
    if is_team_child:
        return True
    return confirmed < event.places - held_places(event, team_taken, now or timezone.now())


def places_left_for(event: Event, *, is_team_child: bool) -> int:
    """The places a family can still get, as the session's page says it:
    the held ones don't count for a family outside the team."""
    confirmed = Registration.objects.filter(event=event, waiting_list=False).count()
    left = event.places - confirmed
    if is_team_child:
        return max(0, left)
    return max(0, left - held_places(event, team_confirmed(event)))
