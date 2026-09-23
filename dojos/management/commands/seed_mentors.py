import random
from datetime import date
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from dojos.models import Dojo, Mentor
from dojos.template_icons import TEMPLATE_ICONS, TEMPLATE_ICONS_DIR

AVATARS_DIR = Path(__file__).resolve().parent.parent.parent / "seed_data" / "avatars"
AVATAR_FILES = sorted(AVATARS_DIR.glob("*.svg"))

# Ninjas (the kids) get a more playful pool — aliens, robots, animals —
# instead of the plain human avatars used for adult mentor roles.
KID_AVATARS_DIR = Path(__file__).resolve().parent.parent.parent / "seed_data" / "kid_avatars"
KID_AVATAR_FILES = sorted(KID_AVATARS_DIR.glob("*.svg"))

FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Sophie", "Lucas", "Mila", "Finn",
    "Lotte", "Milan", "Fien", "Arthur", "Marie", "Louis", "Anna", "Jules",
]
LAST_NAMES = [
    "Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes",
    "Goossens", "Wouters", "De Smet", "Dubois", "Lambert", "Simon", "Michel",
]

TITLES = [
    "Software engineer", "Data analyst", "UX designer", "Product manager",
    "Teacher", "Systems administrator", "Student", "Freelance developer",
]

# The organisation-wide board (Mentor.dojo=None) — these are the people
# shown in "Meet the team" on the homepage, since that page isn't tied to
# a single dojo.
BOARD_MEMBERS = [
    {
        "name": "Priya Nair",
        "title": "Chair, software engineer",
        "bio": "Priya co-founded the Belgian chapter network and now chairs the board, "
               "focusing on keeping every dojo funded and stocked with mentors.",
        "joined_date": date(2019, 3, 1),
        "focus_areas": "Chapter growth, Partnerships",
    },
    {
        "name": "Tom Vermeulen",
        "title": "Treasurer, accountant",
        "bio": "Tom keeps the books straight across every dojo's small grants and sponsor "
               "contributions, and helps new chapters get set up financially.",
        "joined_date": date(2020, 9, 1),
        "focus_areas": "Finance, Grants",
    },
    {
        "name": "Nathalie Coppens",
        "title": "Volunteer coordinator",
        "bio": "Nathalie matches new mentor sign-ups to dojos that need them, and runs the "
               "onboarding session every mentor goes through before their first Saturday.",
        "joined_date": date(2021, 1, 1),
        "focus_areas": "Volunteer recruitment, Onboarding",
    },
    {
        "name": "Bram Van Acker",
        "title": "Partnerships lead",
        "bio": "Bram builds relationships with local libraries, schools and companies willing "
               "to host a dojo or sponsor equipment.",
        "joined_date": date(2022, 6, 1),
        "focus_areas": "Partnerships, Events",
    },
]

# Per-dojo mentors that fill out each chapter's own "Run by" section.
ROLE_WEIGHTS = {Mentor.NINJA: 40, Mentor.VOLUNTEER: 60}

# The dojo's own personalized tagline (shown between the title and the
# buttons — see dojos/dojo_detail.html) and, for a couple of dojos, a longer
# Markdown "About this dojo" blurb (shown further down, above the team) —
# just enough to demonstrate the two spots are independently customizable.
DOJO_TAGLINE = "Seeing a kid's face light up when their code finally runs — that's the whole job."
DOJO_DESCRIPTION = (
    "### What makes us different\n\n"
    "We've been running since our very first Saturday in the local library, and it's still "
    "mentors and ninjas building things together — no lectures, no pressure.\n\n"
    "**Everyone is welcome:** siblings, first-timers, and kids who've been coming for years "
    "all work side by side."
)
DOJO_VISIT_NOTES = (
    "### Parking\n\n"
    "Free parking is available right outside — look for the visitor spots near the main entrance.\n\n"
    "### Getting in\n\n"
    "Enter through the side door and follow the signs; someone will be there to greet you from 15 minutes before the start."
)


def email_for(name, domain):
    # Ninjas (minors, first-name-only) never get one — see the role check
    # at each call site.
    return f"{slugify(name).replace('-', '.')}@{domain}"


def assign_avatar(mentor, rng):
    """Give a mentor without a photo one of the placeholder avatar SVGs
    (dojos/seed_data/avatars/ for adults, dojos/seed_data/kid_avatars/ for
    ninjas), the way seed_pathways.py assigns pathway icons from
    pathways/seed_data/images/."""
    pool = KID_AVATAR_FILES if mentor.role == Mentor.NINJA else AVATAR_FILES
    avatar_path = rng.choice(pool)
    with open(avatar_path, "rb") as f:
        mentor.photo.save(avatar_path.name, File(f), save=True)


def assign_dojo_icon(dojo, rng):
    """Same idea as assign_avatar(), for the round icon at the top of a
    dojo's own page — dojos.template_icons.TEMPLATE_ICONS, the same list
    the dojo owner's own "choose from templates" icon picker uses."""
    filename, _label = rng.choice(TEMPLATE_ICONS)
    icon_path = TEMPLATE_ICONS_DIR / filename
    with open(icon_path, "rb") as f:
        dojo.icon.save(icon_path.name, File(f), save=True)


class Command(BaseCommand):
    help = "Seed the organisation-wide board and a handful of mentors for every dojo."

    def handle(self, *args, **options):
        rng = random.Random(7)
        created = 0

        for member in BOARD_MEMBERS:
            mentor, was_created = Mentor.objects.get_or_create(
                name=member["name"], dojo=None, role=Mentor.BOARD,
                defaults={
                    "title": member["title"],
                    "email": email_for(member["name"], "coderdojobelgium.example"),
                    "bio": member["bio"],
                    "joined_date": member["joined_date"],
                    "focus_areas": member["focus_areas"],
                },
            )
            if was_created:
                assign_avatar(mentor, rng)
            created += 1 if was_created else 0

        for i, dojo in enumerate(Dojo.objects.all()):
            dojo_dirty_fields = []
            if not dojo.tagline:
                dojo.tagline = DOJO_TAGLINE
                dojo_dirty_fields.append("tagline")
            if i < 2 and not dojo.description:
                dojo.description = DOJO_DESCRIPTION
                dojo_dirty_fields.append("description")
            if i < 2 and not dojo.visit_notes:
                dojo.visit_notes = DOJO_VISIT_NOTES
                dojo_dirty_fields.append("visit_notes")
            if dojo_dirty_fields:
                dojo.save(update_fields=dojo_dirty_fields)
            if not dojo.icon:
                assign_dojo_icon(dojo, rng)

            if dojo.owner and not dojo.mentors.filter(role=Mentor.LEAD_COACH).exists():
                # The Lead Coach is always the dojo's real owner login, not
                # a made-up name — see Mentor's docstring on owner_account.
                first, last = dojo.owner.first_name, dojo.owner.last_name
                lead_coach = Mentor.objects.create(
                    name=f"{first} {last}".strip() or dojo.owner.get_username(),
                    dojo=dojo,
                    role=Mentor.LEAD_COACH,
                    owner_account=dojo.owner,
                    title=rng.choice(TITLES),
                    email=dojo.owner.email,
                    bio=f"{first} founded {dojo.name} and has run it ever since.",
                    joined_date=date(rng.randint(2018, 2023), rng.randint(1, 12), 1),
                    sessions_run=rng.randint(20, 120),
                )
                assign_avatar(lead_coach, rng)
                created += 1

            if dojo.mentors.exclude(role=Mentor.LEAD_COACH).exists():
                continue
            for _ in range(rng.randint(2, 4)):
                first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
                # Ninjas are the kids: first name only, no job title.
                role = rng.choices(list(ROLE_WEIGHTS), weights=list(ROLE_WEIGHTS.values()))[0]
                is_ninja = role == Mentor.NINJA
                mentor = Mentor.objects.create(
                    name=first if is_ninja else f"{first} {last}",
                    dojo=dojo,
                    role=role,
                    title="" if is_ninja else rng.choice(TITLES),
                    email="" if is_ninja else email_for(f"{first} {last}", "coderdojo-demo.example"),
                    joined_date=date(rng.randint(2020, 2025), rng.randint(1, 12), 1),
                    sessions_run=rng.randint(1, 40),
                )
                assign_avatar(mentor, rng)
                created += 1

        # A single demo example of the other promotion path: a ninja can be
        # flagged CHAMPION too (a distinct, honorary role — not the Lead
        # Coach) once someone with admin rights decides to recognise them.
        # No account link here — that'd need a real ChildAccount, which
        # this seed data doesn't fabricate.
        first_dojo = Dojo.objects.first()
        if first_dojo and not first_dojo.mentors.filter(role=Mentor.CHAMPION).exists():
            standout_ninja = first_dojo.mentors.filter(role=Mentor.NINJA).first()
            if standout_ninja:
                standout_ninja.role = Mentor.CHAMPION
                standout_ninja.bio = (
                    f"{standout_ninja.name} has been coming to {first_dojo.name} for years and now "
                    "helps run sessions — promoted to Dojo champion in recognition of that."
                )
                standout_ninja.save(update_fields=["role", "bio"])

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} mentors."))
