"""Journeys: standing campaigns (DATA_MODEL.md §11, Tier 3). run() (beat,
daily) sends each active journey's mail to everyone who matches its segment
today, wants that kind of mail, and hasn't had it within its cool-down.
Paired with a "changed recently" rule (stage_changed), that's a triggered
mail: "we miss you" the week a child becomes at risk. Every change of a
journey goes through here; the dashboard views only call these."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from campaigns.models import Campaign, Journey, JourneyDelivery
from campaigns.segmentation.resolver import SegmentResolver
from campaigns.services import CampaignError, launch_problems
from mailing.preferences import subscribed_q
from mailing.services import send

if TYPE_CHECKING:
    from accounts.models import User
    from mailing.models import EmailMessage


def problems(journey: Journey) -> list[str]:
    """What stops the journey from running: the same checks as a campaign's."""
    stand_in = Campaign(category=journey.category, template_key=journey.template_key, segment=journey.segment)
    return [p for p in launch_problems(stand_in) if p != "Only a draft can be launched."]


def audience(journey: Journey) -> "QuerySet[User]":
    if journey.segment is None:
        return SegmentResolver().resolve_definition(None)
    return SegmentResolver().resolve(journey.segment).filter(subscribed_q(journey.category))


def due(journey: Journey, now: datetime | None = None) -> "QuerySet[User]":
    """Who gets it on the next run: matching now, and not within the cool-down."""
    now = now or timezone.now()
    recent = JourneyDelivery.objects.filter(
        journey=journey, created_at__gte=now - timedelta(days=journey.cooldown_days)
    )
    return audience(journey).exclude(pk__in=recent.values("user_id"))


def activate(journey: Journey) -> None:
    if found := problems(journey):
        raise CampaignError(_(" ").join(found))
    journey.is_active = True
    journey.activated_at = timezone.now()
    journey.save(update_fields=["is_active", "activated_at"])


def pause(journey: Journey) -> None:
    journey.is_active = False
    journey.save(update_fields=["is_active"])


def send_test(journey: Journey, user: "User") -> "EmailMessage":
    if not user.email:
        raise CampaignError(_("Your account has no email address to send the test to."))
    return send(user, journey.category, journey.template_key, journey.context, test=True)


def run_one(journey: Journey, now: datetime | None = None) -> int:
    """Send the journey's mail to everyone due. Returns how many."""
    now = now or timezone.now()
    today = timezone.localdate()
    sent = 0
    for user in due(journey, now).order_by("pk").iterator(chunk_size=500):
        email = send(
            user,
            journey.category,
            journey.template_key,
            journey.context,
            idempotency_key=f"journey:{journey.pk}:{user.pk}:{today:%Y%m%d}",
        )
        JourneyDelivery.objects.create(journey=journey, user=user, email=email)
        sent += 1
    return sent


def run(now: datetime | None = None) -> dict[int, int]:
    """All active journeys whose checks pass. Returns {journey id: sent}."""
    return {
        journey.pk: run_one(journey, now)
        for journey in Journey.objects.filter(is_active=True)
        if not problems(journey)
    }


def stats(journey: Journey, days: int = 30) -> dict[str, int]:
    since = timezone.now() - timedelta(days=days)
    deliveries = JourneyDelivery.objects.filter(journey=journey)
    return {
        "total": deliveries.count(),
        "recent": deliveries.filter(created_at__gte=since).count(),
        "sent": deliveries.filter(email__status="sent").count(),
        "held_back": deliveries.filter(email__status="suppressed").count(),
        "due": due(journey).count() if journey.segment_id else 0,
        "days": days,
    }
