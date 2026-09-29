"""Which families belong to a dojo, for the dojo's `dojo_news` mail
(DATA_MODEL.md §25): a child has it as home dojo, or came to one of its
sessions in the last MAILING_DOJO_NEWS_ACTIVE_DAYS days. The family is the
child's guardians, plus the child's own login. The automated "new
sessions" mail (mailing.automated.announce_new_sessions) and the Mail
preferences page's dojo switches both use this one definition."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from dojos.models import Dojo
from events.models import Registration


def active_since(now=None):
    """The start of the window in which a visit makes a child part of a dojo."""
    return (now or timezone.now()) - timedelta(days=settings.MAILING_DOJO_NEWS_ACTIVE_DAYS)


def ninjas_of(dojo, since):
    """The children who belong to `dojo`."""
    visited = Registration.objects.filter(event__dojo=dojo, attended=True, event__start_time__gte=since)
    return Ninja.objects.filter(Q(home_dojo=dojo) | Q(pk__in=visited.values("ninja_id")))


def family_accounts(dojo, since):
    """The active accounts with an email that `dojo`'s news goes to: the
    guardians of its children and those children's own logins. Whether each
    one wants it is send()'s business."""
    ninjas = ninjas_of(dojo, since)
    return (
        User.objects.filter(
            Q(pk__in=Guardianship.objects.filter(ninja__in=ninjas).values("guardian_id"))
            | Q(pk__in=ninjas.exclude(account=None).values("account_id")),
            is_active=True,
        )
        .exclude(email="")
        .order_by("id")
    )


def dojos_of(user, since):
    """The dojos whose news reaches `user`: those of the account's children,
    or of the child itself for a ninja's own login."""
    ninjas = Ninja.objects.filter(
        Q(pk__in=Guardianship.objects.filter(guardian=user).values("ninja_id")) | Q(account=user)
    )
    visited = Registration.objects.filter(ninja__in=ninjas, attended=True, event__start_time__gte=since)
    return Dojo.objects.filter(Q(pk__in=ninjas.values("home_dojo")) | Q(pk__in=visited.values("event__dojo")))
