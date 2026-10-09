"""The public site's cached content lists (core.caching, CAPACITY.md
"Caching"): the same for every visitor, kept in the cache and cleared
whenever a row they're built from is saved or deleted (connect(), from
ContentConfig.ready). Rendered per request, so the visitor's language still
applies (`localized` reads the cached rows' translations)."""

import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from core.caching import cached, clear_on_change

if TYPE_CHECKING:
    from pathways.models import Pathway

    from .models import FAQ, OrganisationTeamMember, Promotion, Sponsor, Testimonial

TIMEOUT = 3600
PROMOTION_TIMEOUT = 300  # at most; less when a promotion starts or ends sooner

PATHWAYS_KEY = "content:pathways"
TEAM_KEY = "content:organisation-team"
FAQS_KEY = "content:global-faqs"
TESTIMONIALS_KEY = "content:global-testimonials"
SPONSORS_KEY = "content:sponsors"
PROMOTIONS_KEY = "content:promotions:{placement}"


def pathways() -> "list[Pathway]":
    from pathways.models import Pathway

    return cached(PATHWAYS_KEY, lambda: list(Pathway.objects.all()), TIMEOUT)


def organisation_team() -> "list[OrganisationTeamMember]":
    """The organisation's public team listing (the homepage's "Meet the team")."""
    from .models import OrganisationTeamMember

    return cached(TEAM_KEY, lambda: list(OrganisationTeamMember.objects.filter(is_public=True)), TIMEOUT)


def global_faqs() -> "list[FAQ]":
    from .models import FAQ

    return cached(FAQS_KEY, lambda: list(FAQ.objects.global_faqs()), TIMEOUT)


def random_testimonial() -> "Testimonial | None":
    """A different site-wide quote on every load: the handful of them is
    cached, the pick is made per request."""
    from .models import Testimonial

    testimonials = cached(TESTIMONIALS_KEY, lambda: list(Testimonial.objects.filter(dojo=None)), TIMEOUT)
    return random.choice(testimonials) if testimonials else None  # noqa: S311 — not security, a random quote


def public_sponsors() -> "list[Sponsor]":
    from .models import Sponsor

    return cached(SPONSORS_KEY, lambda: list(Sponsor.objects.filter(is_public=True)), TIMEOUT)


def _next_change(placement: str, now: datetime) -> datetime | None:
    """When what `placement` shows next changes by time alone: a promotion
    starting or ending, or its event starting or finishing."""
    from .models import Promotion

    moments: list[datetime] = []
    for promotion in Promotion.objects.filter(placement=placement, event__end_time__gt=now):
        moments += [promotion.starts_at, promotion.effective_end, promotion.event.end_time]
    future = [moment for moment in moments if moment > now]
    return min(future) if future else None


def promotions_showing(placement: str) -> "list[Promotion]":
    """Promotion.objects.showing(placement), cached until the next promotion
    starts or ends (at most PROMOTION_TIMEOUT)."""
    from .models import Promotion

    def build() -> "tuple[list[Promotion], int]":
        now = timezone.now()
        showing = list(Promotion.objects.showing(placement, now=now))
        change = _next_change(placement, now)
        seconds = PROMOTION_TIMEOUT
        if change is not None:
            seconds = max(1, min(seconds, int((change - now) / timedelta(seconds=1)) + 1))
        return showing, seconds

    showing, _seconds = cached(
        PROMOTIONS_KEY.format(placement=placement), build, lambda value: value[1], name="content:promotions"
    )
    return showing


def promotion_keys() -> list[str]:
    from .models import Promotion

    return [PROMOTIONS_KEY.format(placement=placement) for placement, _label in Promotion.PLACEMENT_CHOICES]


def connect() -> None:
    from dojos.models import Dojo
    from events.models import Event
    from pathways.models import Pathway

    from .models import FAQ, OrganisationTeamMember, Promotion, Sponsor, Testimonial

    clear_on_change([PATHWAYS_KEY], Pathway)
    clear_on_change([TEAM_KEY], OrganisationTeamMember)
    clear_on_change([FAQS_KEY], FAQ)
    clear_on_change([TESTIMONIALS_KEY], Testimonial)
    clear_on_change([SPONSORS_KEY], Sponsor)
    # A promotion shows only for a visible event of an active dojo, with its
    # title and image.
    clear_on_change(promotion_keys(), Promotion, Event, Dojo)
