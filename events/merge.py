"""Moving what a duplicate child card holds onto the card that stays
(privacy.merge, DATA_MODEL.md §4): registrations (events.registrations),
cancellations, badges, belts. The engagement figures of the card that goes
are dropped, the nightly rebuild counts the merged history."""

from typing import TYPE_CHECKING

from django.db import transaction

from . import registrations
from .models import NinjaBadge, NinjaBelt, NinjaEngagement, NinjaEngagementChange, RegistrationCancellation

if TYPE_CHECKING:
    from accounts.models import Ninja


def move_history(source: "Ninja", target: "Ninja") -> None:
    """Everything `source` has done at a dojo now belongs to `target`."""
    with transaction.atomic():
        registrations.move_registrations(source, target)
        for cancellation in RegistrationCancellation.objects.filter(ninja=source):
            cancellation.ninja = target
            cancellation.save(update_fields=["ninja"])
        held = {badge.badge_id: badge for badge in NinjaBadge.objects.filter(ninja=target)}
        for badge in NinjaBadge.objects.filter(ninja=source):
            twin = held.get(badge.badge_id)
            if twin is None:
                badge.ninja = target
                badge.save(update_fields=["ninja"])
                continue
            # The same badge twice: the one earned first stays, the other goes.
            if badge.earned_date and (twin.earned_date is None or badge.earned_date < twin.earned_date):
                twin.earned_date = badge.earned_date
                twin.save(update_fields=["earned_date"])
            badge.delete()
        for belt in NinjaBelt.objects.filter(ninja=source):
            belt.ninja = target
            belt.save(update_fields=["ninja"])
        NinjaEngagementChange.objects.filter(ninja=source).delete()
        NinjaEngagement.objects.filter(ninja=source).delete()
