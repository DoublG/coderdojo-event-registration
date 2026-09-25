import random
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Ninja
from core.image_library import use_library_image
from dojos.models import Dojo
from pathways.models import Pathway

from ...models import Badge, Belt, Event, NinjaBadge, NinjaBelt, Registration
from .seed_events import SESSION_NAMES, assign_event_team, assign_session_image, description_for

HISTORY_START = date(2020, 1, 1)
SESSION_SLOT = (14, 0, 3)  # 14:00 start, 3 hours long — matches a typical Saturday workshop


# The attendance wristbands — first visit gets white, then green/red/black
# at 5/10/15 visits. Each is a milestone Badge: unlocked by a repeat-count
# threshold rather than a one-off thing you either did or didn't.
BANDS = [
    {"name": "White Band", "threshold": 1, "icon": "band-white.svg", "description": "Came to their first CoderDojo session."},
    {"name": "Green Band", "threshold": 5, "icon": "band-green.svg", "description": "Back for the fifth time — a regular in the making."},
    {"name": "Red Band", "threshold": 10, "icon": "band-red.svg", "description": "Ten sessions in — a genuine dojo regular."},
    {"name": "Black Band", "threshold": 15, "icon": "band-black.svg", "description": "Fifteen sessions. A CoderDojo veteran."},
]

# One-off Badges — no counter, tied to attending one specific event.
SKILL_BADGES = [
    {"name": "Code Explorer", "icon": None, "description": "Tried a pathway all the way through to a finished project.", "criteria": "Complete a pathway project."},
    {"name": "Game Maker", "icon": None, "description": "Built a working game from scratch (pun intended).", "criteria": "Build and share a playable game."},
]
GIRLS_EVENT_BADGE = {
    "name": "CoderDojo for Girls", "icon": "band-pink.svg",
    "description": "Came along to a CoderDojo for Girls session.", "criteria": "Attend a CoderDojo for Girls session.",
}
COOLEST_PROJECTS_BADGE = {
    "name": "Coolest Projects 2026", "icon": "coolest-projects.svg",
    "description": "Showed off a project at Coolest Projects 2026.", "criteria": "Attend Coolest Projects 2026.",
}


# The belt track: a ninja's proficiency level (not attendance — that's the
# wristbands above). One overall track, awarded by a dojo's champion/mentors.
BELTS = [
    (1, "White belt", "#ffffff", "Opens a coding tool and follows a guided project."),
    (2, "Yellow belt", "#f5c518", "Finishes a beginner project on their own."),
    (3, "Orange belt", "#f28c28", "Changes a project to make it their own: new sprites, rules or levels."),
    (4, "Green belt", "#2e9e4f", "Uses variables, loops and conditions without help."),
    (5, "Blue belt", "#2f6fdf", "Plans and builds a small project of their own from scratch."),
    (6, "Purple belt", "#7b3fbf", "Finds and fixes bugs in their own and other ninjas' code."),
    (7, "Brown belt", "#7a4a26", "Builds a complete project in a text-based language (Python, JavaScript, ...)."),
    (8, "Red belt", "#c62828", "Helps other ninjas and explains how their code works."),
    (9, "Black belt", "#111111", "Builds and presents an ambitious project, e.g. at Coolest Projects."),
]


def assign_icon(award, filename):
    use_library_image(award, "icon", "awards", filename, save=True)


def past_saturdays(start, end):
    day = end - timedelta(days=(end.weekday() - 5) % 7 or 7)  # last Saturday before `end`
    dates = []
    while day > start:
        dates.append(day)
        day -= timedelta(days=7)
    return dates


class Command(BaseCommand):
    help = (
        "Seed past Events (2020 onwards) plus Registration, badge and belt history for "
        "existing Ninjas, so the child detail page's Event history, Belt and Badges "
        "sections have something to show."
    )

    def handle(self, *args, **options):
        today = timezone.localdate()

        milestones = []
        for band in BANDS:
            award, was_created = Badge.objects.get_or_create(
                name=band["name"], kind=Badge.MILESTONE,
                defaults={"threshold": band["threshold"], "description": band["description"]},
            )
            if was_created:
                assign_icon(award, band["icon"])
            milestones.append(award)
        milestones.sort(key=lambda a: a.threshold)

        skill_badges = []
        for badge in SKILL_BADGES:
            award, _ = Badge.objects.get_or_create(
                name=badge["name"], kind=Badge.ONE_OFF, defaults={"description": badge["description"], "criteria": badge["criteria"]},
            )
            skill_badges.append(award)

        girls_badge, was_created = Badge.objects.get_or_create(
            name=GIRLS_EVENT_BADGE["name"], kind=Badge.ONE_OFF,
            defaults={"description": GIRLS_EVENT_BADGE["description"], "criteria": GIRLS_EVENT_BADGE["criteria"]},
        )
        if was_created:
            assign_icon(girls_badge, GIRLS_EVENT_BADGE["icon"])

        coolest_badge, was_created = Badge.objects.get_or_create(
            name=COOLEST_PROJECTS_BADGE["name"], kind=Badge.ONE_OFF,
            defaults={"description": COOLEST_PROJECTS_BADGE["description"], "criteria": COOLEST_PROJECTS_BADGE["criteria"]},
        )
        if was_created:
            assign_icon(coolest_badge, COOLEST_PROJECTS_BADGE["icon"])

        belts = [
            Belt.objects.get_or_create(
                level=level, defaults={"name": name, "colour": colour, "requirements": requirements},
            )[0]
            for level, name, colour, requirements in BELTS
        ]

        dates = past_saturdays(HISTORY_START, today)
        hour, minute, duration_hours = SESSION_SLOT

        # Deterministic per-entity RNGs (seeded from the object's own id)
        # rather than one shared sequential Random — that way each dojo's/
        # ninja's choices stay identical across reruns regardless of
        # queryset ordering or how many rows already exist, which is what
        # actually makes get_or_create()'s idempotency hold in practice.
        past_events_by_dojo = {}
        events_created = 0
        # Not draft dojos: they haven't run anything yet. Dormant and archived
        # ones keep their history (it stays in ninjas' own pages).
        for dojo in Dojo.objects.exclude(location=None).exclude(status=Dojo.DRAFT).order_by("id"):
            dojo_rng = random.Random(f"history-dojo-{dojo.id}")
            # ~6 years of history at roughly monthly cadence per dojo.
            dojo_events = []
            for event_date in dojo_rng.sample(dates, k=min(len(dates), dojo_rng.randint(30, 45))):
                start_dt = timezone.make_aware(
                    datetime.combine(event_date, datetime.min.time()).replace(hour=hour, minute=minute)
                )
                end_dt = start_dt + timedelta(hours=duration_hours)
                session_name = dojo_rng.choice(SESSION_NAMES)
                event, was_created = Event.objects.get_or_create(
                    dojo=dojo, start_time=start_dt,
                    defaults={
                        "name": session_name,
                        "status": Event.CLOSED,
                        "end_time": end_dt,
                        "places": dojo_rng.choice([15, 20, 24, 30]),
                        "location": dojo.location,
                        "description": description_for(session_name),
                    },
                )
                if was_created:
                    assign_event_team(event, max_mentors=1)
                    event.pathways.set(dojo.pathways.all())
                    assign_session_image(event, session_name)
                    events_created += 1
                dojo_events.append(event)
            past_events_by_dojo[dojo.id] = sorted(dojo_events, key=lambda e: e.id)

        all_past_events = sorted(
            {e.id: e for events in past_events_by_dojo.values() for e in events}.values(),
            key=lambda e: e.id,
        )

        # Two real one-off historical events, each tied to its own one-off Badge.
        special_created = 0
        girls_event = None
        if all_past_events:
            girls_dojo = all_past_events[0].dojo
            girls_event, was_created = Event.objects.get_or_create(
                dojo=girls_dojo, name="CoderDojo for Girls",
                start_time=timezone.make_aware(datetime(2023, 2, 11, 10, 0)),
                defaults={
                    "end_time": timezone.make_aware(datetime(2023, 2, 11, 13, 0)),
                    "places": 30, "location": girls_dojo.location, "status": Event.CLOSED,
                    "description": "A CoderDojo for Girls session, run for the International Day of Women and Girls in Science.",
                },
            )
            if was_created:
                assign_event_team(girls_event)
            special_created += 1 if was_created else 0

            projects_dojo = all_past_events[-1].dojo
            coolest_event, was_created = Event.objects.get_or_create(
                dojo=projects_dojo, name="Coolest Projects 2026",
                start_time=timezone.make_aware(datetime(2026, 6, 6, 10, 0)),
                defaults={
                    "end_time": timezone.make_aware(datetime(2026, 6, 6, 17, 0)),
                    "places": 200, "location": projects_dojo.location, "status": Event.CLOSED,
                    "description": "CoderDojo's yearly showcase — ninjas demo the projects they've been building all year.",
                },
            )
            if was_created:
                assign_event_team(coolest_event)
            special_created += 1 if was_created else 0
        else:
            coolest_event = None

        # Past sessions took place: closed, not draft (the model default, which
        # hides a session from the public site and from "active" segments).
        # Backfills history seeded before status was set here.
        past_ids = [e.id for e in all_past_events] + [e.id for e in (girls_event, coolest_event) if e is not None]
        Event.objects.filter(pk__in=past_ids, status=Event.DRAFT).update(status=Event.CLOSED)

        pathways = list(Pathway.objects.order_by("id"))
        registrations_created = 0
        awards_created = 0
        belts_created = 0

        for ninja in Ninja.objects.order_by("id"):
            # Seed string kept from before the Participant → Ninja rename, so reruns
            # on an existing database reproduce the same choices.
            p_rng = random.Random(f"history-participant-{ninja.id}")
            candidate_events = past_events_by_dojo.get(ninja.home_dojo_id) or all_past_events
            if not candidate_events:
                continue

            attended_count = 0
            attended_events = []
            for event in p_rng.sample(candidate_events, k=min(len(candidate_events), p_rng.randint(0, 25))):
                attended = p_rng.random() < 0.85  # the odd no-show, otherwise present
                registration, was_created = Registration.objects.get_or_create(
                    event=event, ninja=ninja,
                    defaults={"waiting_list": False, "position": 1, "attended": attended},
                )
                if was_created:
                    # What this ninja worked on: a subset of what the session
                    # covered. Its own RNG: drawing from p_rng only for new
                    # rows would shift every later choice on a rerun.
                    r_rng = random.Random(f"history-registration-{event.id}-{ninja.id}")
                    covered = list(event.pathways.all()) or pathways
                    if covered and r_rng.random() < 0.8:
                        registration.pathways.set(r_rng.sample(covered, k=r_rng.randint(1, min(2, len(covered)))))
                registrations_created += 1 if was_created else 0
                attended_count += attended
                if attended:
                    attended_events.append(event)

            # Belt history: roughly one belt per four sessions attended, each
            # awarded at one of those sessions by its team. The
            # coin flip is drawn every time so reruns keep the same RNG stream.
            extra_belt = p_rng.random() < 0.5
            if belts and attended_events and not ninja.belts.exists():
                attended_events.sort(key=lambda e: e.start_time)
                reached = min(len(belts), len(attended_events) // 4 + extra_belt)
                for belt, event in zip(belts[:reached], attended_events[::4], strict=False):
                    # Awarded by one of that session's champion/mentors (own RNG,
                    # so it doesn't shift the ninja's other choices).
                    awarders = [m for m in event.team.all() if m.role in m.MANAGER_ROLES]
                    if not awarders:
                        break
                    awarder = random.Random(f"belt-{ninja.id}-{belt.level}").choice(awarders)
                    NinjaBelt.objects.create(
                        ninja=ninja, belt=belt, awarded_on=event.start_time.date(),
                        awarded_by=awarder.user, awarded_as_membership=awarder, awarded_as_role=awarder.role,
                    )
                    belts_created += 1

            # Every wristband tier actually reached is earned; the very
            # next tier up (if any) shows as locked-with-progress.
            for milestone in milestones:
                if attended_count >= milestone.threshold:
                    _, was_created = NinjaBadge.objects.get_or_create(
                        ninja=ninja, badge=milestone,
                        defaults={
                            "earned_date": today - timedelta(days=p_rng.randint(10, 5 * 365)),
                            "progress_current": milestone.threshold,
                            "progress_total": milestone.threshold,
                        },
                    )
                    awards_created += 1 if was_created else 0
                else:
                    _, was_created = NinjaBadge.objects.get_or_create(
                        ninja=ninja, badge=milestone,
                        defaults={"progress_current": attended_count, "progress_total": milestone.threshold},
                    )
                    awards_created += 1 if was_created else 0
                    break

            if pathways and p_rng.random() < 0.5:
                skill_award = p_rng.choice(skill_badges)
                _, was_created = NinjaBadge.objects.get_or_create(
                    ninja=ninja, badge=skill_award,
                    defaults={
                        "earned_date": (
                            today - timedelta(days=p_rng.randint(5, 5 * 365)) if p_rng.random() < 0.5 else None
                        ),
                    },
                )
                awards_created += 1 if was_created else 0

            # A one-in-six chance of having gone to each special event —
            # attending it is what creates the badge, matching how the
            # wristbands work off real Registration rows too.
            if girls_event and p_rng.random() < 1 / 6:
                _, was_created = Registration.objects.get_or_create(
                    event=girls_event, ninja=ninja,
                    defaults={"waiting_list": False, "position": 1, "attended": True},
                )
                registrations_created += 1 if was_created else 0
                _, was_created = NinjaBadge.objects.get_or_create(
                    ninja=ninja, badge=girls_badge,
                    defaults={"earned_date": girls_event.start_time.date()},
                )
                awards_created += 1 if was_created else 0

            if coolest_event and p_rng.random() < 1 / 6 and coolest_event.start_time.date() <= today:
                _, was_created = Registration.objects.get_or_create(
                    event=coolest_event, ninja=ninja,
                    defaults={"waiting_list": False, "position": 1, "attended": True},
                )
                registrations_created += 1 if was_created else 0
                _, was_created = NinjaBadge.objects.get_or_create(
                    ninja=ninja, badge=coolest_badge,
                    defaults={"earned_date": coolest_event.start_time.date()},
                )
                awards_created += 1 if was_created else 0

        self.stdout.write(self.style.SUCCESS(
            f"Done. past_events_created={events_created} special_events_created={special_created} "
            f"registrations_created={registrations_created} badges_created={awards_created} "
            f"belts_created={belts_created}."
        ))
