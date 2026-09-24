import random
from datetime import date, datetime, timedelta
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Participant
from dojos.models import Dojo
from pathways.models import Pathway

from .seed_events import SESSION_NAMES, assign_session_image, description_for
from ...models import BadgeAward, Event, MilestoneAward, ParticipantAward, Registration

HISTORY_START = date(2020, 1, 1)
SESSION_SLOT = (14, 0, 3)  # 14:00 start, 3 hours long — matches a typical Saturday workshop

AWARDS_DIR = Path(__file__).resolve().parent.parent.parent / "seed_data" / "awards"

# The attendance wristbands — first visit gets white, then green/red/black
# at 5/10/15 visits. Each is a MilestoneAward: unlocked by a repeat-count
# threshold rather than a one-off thing you either did or didn't.
BANDS = [
    {"name": "White Band", "threshold": 1, "icon": "band-white.svg", "description": "Came to their first CoderDojo session."},
    {"name": "Green Band", "threshold": 5, "icon": "band-green.svg", "description": "Back for the fifth time — a regular in the making."},
    {"name": "Red Band", "threshold": 10, "icon": "band-red.svg", "description": "Ten sessions in — a genuine dojo regular."},
    {"name": "Black Band", "threshold": 15, "icon": "band-black.svg", "description": "Fifteen sessions. A CoderDojo veteran."},
]

# One-off BadgeAwards — no counter, tied to attending one specific event.
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


def assign_icon(award, filename):
    icon_path = AWARDS_DIR / filename
    with open(icon_path, "rb") as f:
        award.icon.save(icon_path.name, File(f), save=True)


def past_saturdays(start, end):
    day = end - timedelta(days=(end.weekday() - 5) % 7 or 7)  # last Saturday before `end`
    dates = []
    while day > start:
        dates.append(day)
        day -= timedelta(days=7)
    return dates


class Command(BaseCommand):
    help = (
        "Seed past Events (2020 onwards) plus Registration/Award history for existing "
        "Participants, so the child detail page's Event history and Awards sections have "
        "something to show."
    )

    def handle(self, *args, **options):
        today = timezone.localdate()

        milestones = []
        for band in BANDS:
            award, was_created = MilestoneAward.objects.get_or_create(
                name=band["name"],
                defaults={"threshold": band["threshold"], "description": band["description"]},
            )
            if was_created:
                assign_icon(award, band["icon"])
            milestones.append(award)
        milestones.sort(key=lambda a: a.threshold)

        skill_badges = []
        for badge in SKILL_BADGES:
            award, _ = BadgeAward.objects.get_or_create(
                name=badge["name"], defaults={"description": badge["description"], "criteria": badge["criteria"]},
            )
            skill_badges.append(award)

        girls_badge, was_created = BadgeAward.objects.get_or_create(
            name=GIRLS_EVENT_BADGE["name"],
            defaults={"description": GIRLS_EVENT_BADGE["description"], "criteria": GIRLS_EVENT_BADGE["criteria"]},
        )
        if was_created:
            assign_icon(girls_badge, GIRLS_EVENT_BADGE["icon"])

        coolest_badge, was_created = BadgeAward.objects.get_or_create(
            name=COOLEST_PROJECTS_BADGE["name"],
            defaults={"description": COOLEST_PROJECTS_BADGE["description"], "criteria": COOLEST_PROJECTS_BADGE["criteria"]},
        )
        if was_created:
            assign_icon(coolest_badge, COOLEST_PROJECTS_BADGE["icon"])

        dates = past_saturdays(HISTORY_START, today)
        hour, minute, duration_hours = SESSION_SLOT

        # Deterministic per-entity RNGs (seeded from the object's own id)
        # rather than one shared sequential Random — that way each dojo's/
        # participant's choices stay identical across reruns regardless of
        # queryset ordering or how many rows already exist, which is what
        # actually makes get_or_create()'s idempotency hold in practice.
        past_events_by_dojo = {}
        events_created = 0
        for dojo in Dojo.objects.exclude(location=None).order_by("id"):
            dojo_rng = random.Random(f"history-dojo-{dojo.id}")
            champion = dojo.champion_membership
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
                        "end_time": end_dt,
                        "places": dojo_rng.choice([15, 20, 24, 30]),
                        "location": dojo.location,
                        "description": description_for(session_name),
                    },
                )
                if was_created:
                    if champion:
                        event.team.add(champion)
                    assign_session_image(event, session_name)
                    events_created += 1
                dojo_events.append(event)
            past_events_by_dojo[dojo.id] = sorted(dojo_events, key=lambda e: e.id)

        all_past_events = sorted(
            {e.id: e for events in past_events_by_dojo.values() for e in events}.values(),
            key=lambda e: e.id,
        )

        # Two real one-off historical events, each tied to its own BadgeAward.
        special_created = 0
        girls_event = None
        if all_past_events:
            girls_dojo = all_past_events[0].dojo
            girls_event, was_created = Event.objects.get_or_create(
                dojo=girls_dojo, name="CoderDojo for Girls",
                start_time=timezone.make_aware(datetime(2023, 2, 11, 10, 0)),
                defaults={
                    "end_time": timezone.make_aware(datetime(2023, 2, 11, 13, 0)),
                    "places": 30, "location": girls_dojo.location,
                    "description": "A CoderDojo for Girls session, run for the International Day of Women and Girls in Science.",
                },
            )
            special_created += 1 if was_created else 0

            projects_dojo = all_past_events[-1].dojo
            coolest_event, was_created = Event.objects.get_or_create(
                dojo=projects_dojo, name="Coolest Projects 2026",
                start_time=timezone.make_aware(datetime(2026, 6, 6, 10, 0)),
                defaults={
                    "end_time": timezone.make_aware(datetime(2026, 6, 6, 17, 0)),
                    "places": 200, "location": projects_dojo.location,
                    "description": "CoderDojo's yearly showcase — ninjas demo the projects they've been building all year.",
                },
            )
            special_created += 1 if was_created else 0
        else:
            coolest_event = None

        pathways = list(Pathway.objects.order_by("id"))
        registrations_created = 0
        awards_created = 0

        for participant in Participant.objects.order_by("id"):
            p_rng = random.Random(f"history-participant-{participant.id}")
            candidate_events = past_events_by_dojo.get(participant.home_dojo_id) or all_past_events
            if not candidate_events:
                continue

            attended_count = 0
            for event in p_rng.sample(candidate_events, k=min(len(candidate_events), p_rng.randint(0, 25))):
                attended = p_rng.random() < 0.85  # the odd no-show, otherwise present
                _, was_created = Registration.objects.get_or_create(
                    event=event, participant=participant,
                    defaults={
                        "waiting_list": False,
                        "position": 1,
                        "attended": attended,
                        "pathway": p_rng.choice(pathways) if pathways and p_rng.random() < 0.6 else None,
                    },
                )
                registrations_created += 1 if was_created else 0
                attended_count += attended

            # Every wristband tier actually reached is earned; the very
            # next tier up (if any) shows as locked-with-progress.
            for i, milestone in enumerate(milestones):
                if attended_count >= milestone.threshold:
                    _, was_created = ParticipantAward.objects.get_or_create(
                        participant=participant, award=milestone,
                        defaults={
                            "earned_date": today - timedelta(days=p_rng.randint(10, 5 * 365)),
                            "progress_current": milestone.threshold,
                            "progress_total": milestone.threshold,
                        },
                    )
                    awards_created += 1 if was_created else 0
                else:
                    _, was_created = ParticipantAward.objects.get_or_create(
                        participant=participant, award=milestone,
                        defaults={"progress_current": attended_count, "progress_total": milestone.threshold},
                    )
                    awards_created += 1 if was_created else 0
                    break

            if pathways and p_rng.random() < 0.5:
                skill_award = p_rng.choice(skill_badges)
                _, was_created = ParticipantAward.objects.get_or_create(
                    participant=participant, award=skill_award,
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
                    event=girls_event, participant=participant,
                    defaults={"waiting_list": False, "position": 1, "attended": True},
                )
                registrations_created += 1 if was_created else 0
                _, was_created = ParticipantAward.objects.get_or_create(
                    participant=participant, award=girls_badge,
                    defaults={"earned_date": girls_event.start_time.date()},
                )
                awards_created += 1 if was_created else 0

            if coolest_event and p_rng.random() < 1 / 6 and coolest_event.start_time.date() <= today:
                _, was_created = Registration.objects.get_or_create(
                    event=coolest_event, participant=participant,
                    defaults={"waiting_list": False, "position": 1, "attended": True},
                )
                registrations_created += 1 if was_created else 0
                _, was_created = ParticipantAward.objects.get_or_create(
                    participant=participant, award=coolest_badge,
                    defaults={"earned_date": coolest_event.start_time.date()},
                )
                awards_created += 1 if was_created else 0

        self.stdout.write(self.style.SUCCESS(
            f"Done. past_events_created={events_created} special_events_created={special_created} "
            f"registrations_created={registrations_created} awards_created={awards_created}."
        ))
