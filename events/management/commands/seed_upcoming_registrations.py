import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import ExpressionWrapper, F, FloatField, Max
from django.utils import timezone

from accounts.home_dojo import assign_on_signup
from accounts.models import Ninja
from core.audit import without_audit_log
from dojos.models import Dojo
from geo.functions import DistanceSphere

from ...engagement import is_aimed_at
from ...models import Event, Registration

# The sessions filled up to test the waiting list, one per state worth
# testing: full with children waiting, exactly full (the next sign-up
# waits), one place left (the next sign-up gets in, the one after waits).
# (label, places left empty, children on the waiting list)
FULL_SESSIONS = [
    ("full, with a waiting list", 0, 4),
    ("exactly full", 0, 0),
    ("one place left", 1, 0),
]

# Everyone else: most children are signed up for their home dojo's next
# session, and some also for a session at another dojo nearby.
HOME_SESSION_SHARE = 0.6
OTHER_DOJOS_MIN, OTHER_DOJOS_MAX = 0, 2
NEARBY_KM = 30
NEARBY_DOJOS = 6
# Never take a normal session's last places: only FULL_SESSIONS are full,
# so the other sessions still take a sign-up.
KEEP_FREE = 3


def upcoming_sessions():
    """Open, public sessions still to come that sign up here (not on an
    organisation's external page)."""
    return (
        Event.objects.visible()
        .filter(status=Event.OPEN, start_time__gte=timezone.now(), dojo__kind=Dojo.DOJO, places__gt=0)
        .filter(external_registration_url="")
        .order_by("start_time", "id")
    )


def sign_up(event, ninja, signed_up_at):
    """What events.views.event_signup does, minus the booking mail (seeded
    families aren't told): the next position, the waiting list once the
    session is full, the session's pathways, and the home dojo on a first
    sign-up."""
    registration = Registration.objects.filter(event=event, ninja=ninja).first()
    if registration is not None:
        return registration, False
    position = (Registration.objects.filter(event=event).aggregate(Max("position"))["position__max"] or 0) + 1
    confirmed = Registration.objects.filter(event=event, waiting_list=False).count()
    registration = Registration.objects.create(
        event=event,
        ninja=ninja,
        waiting_list=confirmed >= event.places,
        position=position,
        created_at=signed_up_at,
    )
    registration.pathways.set(event.pathways.all())
    assign_on_signup(ninja, event.dojo)
    return registration, True


def nearby_dojos(dojo):
    """The public dojos closest to `dojo`, nearest first, within NEARBY_KM."""
    if dojo is None or dojo.location is None:
        return []
    return list(
        Dojo.objects.public()
        .exclude(pk=dojo.pk)
        .exclude(location=None)
        .annotate(
            distance_km=ExpressionWrapper(
                DistanceSphere(F("location"), dojo.location) / 1000.0, output_field=FloatField()
            )
        )
        .filter(distance_km__lte=NEARBY_KM)
        .order_by("distance_km", "id")[:NEARBY_DOJOS]
    )


class Command(BaseCommand):
    help = (
        "Sign seeded children up for upcoming sessions: their home dojo's next session and sessions at "
        "other dojos nearby, so children are registered at several dojos. Fills three sessions to test "
        "the waiting list: one full with children waiting, one exactly full, one with one place left. "
        "No mail is sent. Rerun-safe: only adds what's missing."
    )

    @without_audit_log
    def handle(self, *args, **options):
        now = timezone.now()
        sessions = list(upcoming_sessions().select_related("dojo"))
        next_session = {}
        for event in sessions:
            next_session.setdefault(event.dojo_id, event)

        # Children with a guardian (the ones a seeded parent can log in for).
        ninjas = list(
            Ninja.objects.filter(guardianships__isnull=False).distinct().select_related("home_dojo").order_by("id")
        )

        # The full sessions: the next session of the dojos with the most home
        # children, so the families that fill them are mostly its own.
        home_counts = {}
        for ninja in ninjas:
            if ninja.home_dojo_id in next_session:
                home_counts[ninja.home_dojo_id] = home_counts.get(ninja.home_dojo_id, 0) + 1
        busiest = sorted(home_counts, key=lambda dojo_id: (-home_counts[dojo_id], dojo_id))
        full_targets = [
            (next_session[dojo_id], label, left, waiting)
            for dojo_id, (label, left, waiting) in zip(busiest, FULL_SESSIONS, strict=False)
        ]
        full_ids = {event.id for event, *_ in full_targets}

        created = 0
        for event, _label, left, waiting in full_targets:
            fill_rng = random.Random(f"upcoming-full-{event.id}")
            wanted = event.places - left + waiting
            # Its own children first, then the nearest dojos' (children the
            # session is meant for before the others).
            order = {dojo.id: rank for rank, dojo in enumerate(nearby_dojos(event.dojo), start=1)}
            candidates = sorted(
                ninjas,
                key=lambda n: (
                    0 if n.home_dojo_id == event.dojo_id else order.get(n.home_dojo_id, len(order) + 1),
                    not is_aimed_at(n, event),
                    fill_rng.random(),
                ),
            )
            have = Registration.objects.filter(event=event).count()
            for ninja in candidates:
                if have >= wanted:
                    break
                # Signed up over the last two weeks, in queue order.
                _, was_created = sign_up(event, ninja, now - timedelta(days=14) + timedelta(hours=have * 4))
                have += was_created
                created += was_created

        for ninja in ninjas:
            # Own RNG per child, so reruns make the same choices.
            n_rng = random.Random(f"upcoming-ninja-{ninja.id}")
            wanted = []
            home = next_session.get(ninja.home_dojo_id)
            if home is not None and n_rng.random() < HOME_SESSION_SHARE:
                wanted.append(home)
            others = [next_session[d.id] for d in nearby_dojos(ninja.home_dojo) if d.id in next_session]
            wanted += n_rng.sample(others, k=min(len(others), n_rng.randint(OTHER_DOJOS_MIN, OTHER_DOJOS_MAX)))
            for event in wanted:
                if event.id in full_ids or not is_aimed_at(ninja, event):
                    continue
                if Registration.objects.filter(event=event, ninja=ninja).exists():
                    continue
                if event.places_left <= KEEP_FREE:
                    continue
                _, was_created = sign_up(event, ninja, now - timedelta(hours=n_rng.randint(1, 20 * 24)))
                created += was_created

        self.stdout.write(self.style.SUCCESS(f"Done. registrations_created={created}."))
        for event, label, *_ in full_targets:
            waiting = Registration.objects.filter(event=event, waiting_list=True).count()
            self.stdout.write(
                f"  {label}: {event.name} at {event.dojo.name} on {timezone.localtime(event.start_time):%d/%m/%Y}"
                f" (event {event.id}, {event.places - event.places_left}/{event.places} places, {waiting} waiting)"
            )
        multi = Registration.objects.filter(event__in=upcoming_sessions()).values("ninja").distinct().count()
        several = sum(
            1
            for ninja in ninjas
            if Registration.objects.filter(event__in=upcoming_sessions(), ninja=ninja)
            .values("event__dojo")
            .distinct()
            .count()
            > 1
        )
        self.stdout.write(f"  {multi} children signed up for upcoming sessions, {several} of them at several dojos.")
