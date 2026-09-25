"""Who wants which mail. An account's choice per category is a
MailPreference row; without one, the category's default applies
(categories.DEFAULT_SUBSCRIBED). Every change goes through
set_preference(), which also appends a ConsentEvent (proof of consent)."""

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from .categories import CAN_OPT_OUT, DEFAULT_SUBSCRIBED, PRIVACY_WORDING_VERSION, categories_for
from .models import ConsentEvent, MailPreference


def is_subscribed(user, category):
    """Whether `user` wants mail in `category` (and can get it at all)."""
    if category not in categories_for(user):
        return False
    if not CAN_OPT_OUT[category]:
        return True
    choice = MailPreference.objects.filter(user=user, category=category).values_list("subscribed", flat=True).first()
    return DEFAULT_SUBSCRIBED[category] if choice is None else choice


def preferences_for(user):
    """{category: subscribed} for every category the account can receive."""
    stored = dict(MailPreference.objects.filter(user=user).values_list("category", "subscribed"))
    return {
        category: stored.get(category, DEFAULT_SUBSCRIBED[category]) if CAN_OPT_OUT[category] else True
        for category in categories_for(user)
    }


def set_preference(user, category, subscribed, source):
    """Record the account's choice for `category`. Logs a ConsentEvent when
    the effective choice changes. Returns True if it changed. Categories
    that can't be switched off are ignored."""
    if not CAN_OPT_OUT[category] or category not in categories_for(user):
        return False
    with transaction.atomic():
        before = is_subscribed(user, category)
        MailPreference.objects.update_or_create(user=user, category=category, defaults={"subscribed": subscribed})
        if before == subscribed:
            return False
        ConsentEvent.objects.create(
            user=user, category=category, subscribed=subscribed, source=source,
            wording_version=PRIVACY_WORDING_VERSION,
        )
    return True


def subscribed_q(category):
    """A Q on User for "wants mail in `category`", for filtering audiences
    in the database (a campaign never reaches someone who opted out)."""
    choice = MailPreference.objects.filter(user=OuterRef("pk"), category=category)
    if not CAN_OPT_OUT[category]:
        return Q()
    if DEFAULT_SUBSCRIBED[category]:
        return ~Exists(choice.filter(subscribed=False))
    return Exists(choice.filter(subscribed=True))
