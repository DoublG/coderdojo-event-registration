import random
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import OrganisationRole, User
from accounts.seed_credentials import CREDENTIALS_FILE, generate_password, write_credentials
from accounts.template_avatars import TEMPLATE_AVATARS, TEMPLATE_KID_AVATARS
from applications.models import Application
from applications.seeding import approve_for_seeding
from content.models import OrganisationTeamMember
from core.audit import without_audit_log
from core.image_library import use_library_image
from dojos.models import Dojo, DojoMembership
from dojos.template_icons import TEMPLATE_ICONS

AVATAR_FILES = [filename for filename, _label in TEMPLATE_AVATARS]

# Ninjas (the kids) get a more playful pool — aliens, robots, animals —
# instead of the plain human avatars used for adult mentor roles.
KID_AVATAR_FILES = [filename for filename, _label in TEMPLATE_KID_AVATARS]

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

# The organisation's own team (content.OrganisationTeamMember) — shown in
# "Meet the team" on the homepage, since that page isn't tied to a single
# dojo. `title` becomes each person's position.
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

# Mentors per dojo, and how many of them also help at a second dojo.
MENTORS_PER_DOJO = (1, 3)

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
    return f"{slugify(name).replace('-', '.')}@{domain}"


def assign_avatar(obj, rng, kid=False):
    """Give a profile without a photo one of the template avatars
    (accounts.template_avatars: TEMPLATE_AVATARS for adults,
    TEMPLATE_KID_AVATARS for ninjas). Works for an account's team-page
    profile (User.photo) and an OrganisationTeamMember alike. Links the
    shared standard image (core.image_library), no copy made."""
    filename = rng.choice(KID_AVATAR_FILES if kid else AVATAR_FILES)
    use_library_image(obj, "photo", "ninjas" if kid else "mentors", filename, save=True)


def assign_dojo_icon(dojo, rng):
    """Same idea as assign_avatar(), for the round icon at the top of a
    dojo's own page — dojos.template_icons.TEMPLATE_ICONS, the same list
    the dojo owner's own "choose from templates" icon picker uses."""
    filename, _label = rng.choice(TEMPLATE_ICONS)
    use_library_image(dojo, "icon", "dojos", filename, save=True)


# A few board members also get a login with an organisation role (access to
# the management dashboards — the Django admin for now, accounts.organisation).
# Not everyone listed has access, and vice versa.
ORGANISATION_ACCOUNTS = [
    ("Priya Nair", OrganisationRole.ADMIN),
    ("Tom Vermeulen", OrganisationRole.BOARD),
]


class Command(BaseCommand):
    help = (
        "Seed the organisation's team listing (two of them with an organisation-role login), "
        "each dojo champion's team-page profile, "
        "and a few mentor accounts per dojo (adult logins approved as mentors, with active "
        "memberships; some help at two dojos). Also a pending join request and a former "
        "team member here and there, to exercise the Team page."
    )

    @without_audit_log
    def handle(self, *args, **options):
        rng = random.Random(7)
        created = 0
        credential_rows = []

        for order, member in enumerate(BOARD_MEMBERS):
            listed, was_created = OrganisationTeamMember.objects.get_or_create(
                name=member["name"],
                defaults={
                    "position": member["title"],
                    "email": email_for(member["name"], "coderdojobelgium.example"),
                    "bio": member["bio"],
                    "joined_date": member["joined_date"],
                    "focus_areas": member["focus_areas"],
                    "order": order,
                },
            )
            if was_created:
                assign_avatar(listed, rng)

        organisation_rows = []
        for name, role in ORGANISATION_ACCOUNTS:
            username = f"org-{slugify(name)}"
            account = User.objects.filter(username=username).first()
            if account is None:
                first, last = name.split(" ", 1)
                email = email_for(name, "coderdojobelgium.example")
                password = generate_password()
                account = User(username=username, email=email, first_name=first, last_name=last)
                account.set_password(password)
                account.save()
                organisation_rows.append((username, email, password))
                created += 1
            OrganisationRole.objects.get_or_create(account=account, role=role)
            OrganisationTeamMember.objects.filter(name=name, account=None).update(account=account)
        if organisation_rows:
            write_credentials("organisation", organisation_rows)

        mentors_pool = []
        for i, dojo in enumerate(Dojo.objects.order_by("id")):
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

            # The champion's own team-page profile (shared by all their dojos).
            champion = dojo.champion
            if champion is not None and not champion.bio:
                champion.title = rng.choice(TITLES)
                champion.bio = f"{champion.first_name or champion.username} founded {dojo.name} and has run it ever since."
                champion.save(update_fields=["title", "bio"])
                if not champion.photo:
                    assign_avatar(champion, rng)

            if dojo.memberships.filter(role=DojoMembership.MENTOR).exists():
                continue
            for n in range(1, rng.randint(*MENTORS_PER_DOJO) + 1):
                username = f"mentor-{dojo.id}-{n}"
                mentor = User.objects.filter(username=username).first()
                if mentor is None:
                    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
                    email = email_for(f"{first} {last} {dojo.id} {n}", "coderdojo-demo.example")
                    password = generate_password()
                    mentor = User(
                        username=username, email=email, first_name=first, last_name=last,
                        title=rng.choice(TITLES),
                    )
                    mentor.set_password(password)
                    mentor.save()
                    assign_avatar(mentor, rng)
                    credential_rows.append((username, email, password))
                    created += 1
                approve_for_seeding(mentor, Application.MENTOR, rng, mentor_role=Application.VOLUNTEER_MENTOR)
                DojoMembership.objects.get_or_create(
                    dojo=dojo, user=mentor,
                    defaults={
                        "role": DojoMembership.MENTOR,
                        "status": DojoMembership.ACTIVE,
                        "joined_at": timezone.now().replace(year=rng.randint(2020, 2025)),
                    },
                )
                mentors_pool.append(mentor)

        # A few mentors help at a second dojo too, and a few dojos have a
        # pending join request and a former (dormant) team member — so the
        # Team page and the dojo switcher have something to show.
        dojos = list(Dojo.objects.order_by("id"))
        for k, mentor in enumerate(mentors_pool[:3]):
            other = dojos[(k * 7 + 3) % len(dojos)] if dojos else None
            if other is not None and not DojoMembership.objects.filter(dojo=other, user=mentor).exists():
                DojoMembership.objects.create(
                    dojo=other, user=mentor, role=DojoMembership.MENTOR, status=DojoMembership.ACTIVE,
                    joined_at=timezone.now(),
                )
        for k, mentor in enumerate(mentors_pool[3:6]):
            other = dojos[(k * 5 + 1) % len(dojos)] if dojos else None
            if other is not None and not DojoMembership.objects.filter(dojo=other, user=mentor).exists():
                DojoMembership.objects.create(
                    dojo=other, user=mentor, role=DojoMembership.MENTOR,
                    status=DojoMembership.REQUESTED, requested_by=mentor,
                )
        for mentor in mentors_pool[6:8]:
            membership = DojoMembership.objects.filter(user=mentor, status=DojoMembership.ACTIVE).first()
            if membership is not None:
                membership.status = DojoMembership.DORMANT
                membership.left_at = timezone.now()
                membership.save(update_fields=["status", "left_at"])

        # Every seeded mentor is approved (valid check + approved application),
        # including mentors seeded before the onboarding redesign.
        for membership in DojoMembership.objects.filter(role=DojoMembership.MENTOR).select_related("user"):
            if not membership.user.applications.filter(status=Application.APPROVED).exists():
                approve_for_seeding(membership.user, Application.MENTOR, rng, mentor_role=Application.VOLUNTEER_MENTOR)

        if credential_rows:
            write_credentials("mentor", credential_rows)
        self.stdout.write(self.style.SUCCESS(
            f"Done. created={created} mentor accounts. Credentials written to {CREDENTIALS_FILE}"
        ))
