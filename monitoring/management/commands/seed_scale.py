"""A database at the size of a capacity scenario (monitoring.capacity,
CAPACITY.md): dojos with their teams, families and children, a year (or
more) of sessions with bookings, attendance, cancellations, belts and
badges, the mail they cause with real rendered templates, consents, audit
log entries, login sessions and the engagement snapshot. For measuring
bytes per row (`capacity_report --measure`) and for load tests.

Only on a database whose name starts with `test_` (the devcontainer's app
user may create those), never on the dev or production data:

    python manage.py shell -c "..."   # or see CAPACITY.md for creating test_capacity
    DB_NAME=test_capacity python manage.py migrate
    DB_NAME=test_capacity python manage.py seed_scale --scenario growth --years 1

Every synthetic login's password is `--password` (default "scale-test")."""

import random
import uuid
from datetime import date, timedelta

from auditlog.models import LogEntry
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from applications.models import Application
from core.audit import without_audit_log
from dojos.models import Dojo, DojoMembership
from events import engagement
from events.models import (
    Badge,
    Belt,
    Event,
    NinjaBadge,
    NinjaBelt,
    Registration,
    RegistrationCancellation,
    TeamAttendance,
)
from mailing.categories import MailCategory
from mailing.models import ConsentEvent, EmailMessage, MailPreference
from mailing.rendering import render
from mailing.seed_templates import SAMPLE_CONTEXT
from monitoring import capacity
from pathways.models import Pathway

BATCH = 2000
LANGUAGES = ["nl-be", "nl-be", "fr-be", "en-us"]
GIRL_NAMES = ["Emma", "Louise", "Olivia", "Nora", "Lina", "Juliette", "Elise", "Marie"]
BOY_NAMES = ["Noah", "Arthur", "Louis", "Jules", "Lucas", "Adam", "Victor", "Liam"]
FAMILY_NAMES = ["Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes", "Dubois", "Lambert", "Dupont"]
# Which template each kind of mail uses (mailing.automated, campaigns).
MAIL_TEMPLATES = {
    "booking confirmations and waiting-list mail": ("registration_confirmed", MailCategory.REGISTRATION),
    "session reminders": ("session_reminder", MailCategory.REMINDER),
    "new-sessions digests": ("new_sessions_at_dojo", MailCategory.DOJO_NEWS),
    "organisation campaigns": ("campaign_coolest_projects", MailCategory.NEWSLETTER),
    "dojo mailings": ("dojo_message", MailCategory.DOJO_NEWS),
    "journeys": ("campaign_girlz", MailCategory.NEWSLETTER),
    "account mail (sign-up, logins, resets)": ("login_link", MailCategory.SERVICE),
}


def chunks(items, size=BATCH):
    for start in range(0, len(items), size):
        yield items[start : start + size]


class Command(BaseCommand):
    help = "Fill a test_ database with a capacity scenario's data (CAPACITY.md)."

    def add_arguments(self, parser):
        parser.add_argument("--scenario", choices=sorted(capacity.SCENARIOS), default="growth")
        parser.add_argument("--years", type=int, default=1)
        parser.add_argument("--seed", type=int, default=1)
        parser.add_argument("--password", default="scale-test")
        # ANALYZE TABLE commits, which a test's transaction can't have.
        parser.add_argument("--skip-analyze", action="store_true", help="Leave the table statistics as they are.")

    @without_audit_log
    def handle(self, *args, **options):
        name = settings.DATABASES["default"]["NAME"]
        if not name.startswith("test_"):
            raise CommandError(f"Refusing to fill {name!r}: only a database whose name starts with test_.")
        if Dojo.objects.exists():
            raise CommandError(f"{name!r} already has dojos: start from a freshly migrated database.")
        self.s = capacity.SCENARIOS[options["scenario"]]
        self.years = options["years"]
        self.rng = random.Random(options["seed"])
        self.now = timezone.now()
        self.password = make_password(options["password"])
        self.ids = {}
        self.stdout.write(f"Filling {name} with scenario {self.s.name}, {self.years} year(s)...")

        call_command("load_mail_templates", verbosity=0)
        self.pathways = [Pathway.objects.create(name=f"Pathway {i}") for i in range(1, 7)]
        self.make_teams()
        self.make_families()
        self.make_sessions()
        self.make_bookings()
        self.make_awards()
        self.make_mail()
        self.make_consents()
        self.make_audit_log()
        self.make_login_sessions()
        self.step("engagement snapshot", engagement.rebuild())
        self.stdout.write(self.style.SUCCESS("Done."))
        if options["skip_analyze"]:
            return
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            for (table,) in cursor.fetchall():
                cursor.execute(f"ANALYZE TABLE `{table}`")
                cursor.fetchall()

    def next_id(self, model):
        """MySQL's bulk_create doesn't return primary keys: the (fresh)
        database gets them from here instead."""
        self.ids[model] = self.ids.get(model, 0) + 1
        return self.ids[model]

    def step(self, what, count):
        self.stdout.write(f"  {what}: {count:,}")

    def user(self, username, first, last, **fields):
        return User(
            id=self.next_id(User),
            username=username,
            email=f"{username}@scale.example",
            first_name=first,
            last_name=last,
            password=self.password,
            preferred_language=self.rng.choice(LANGUAGES),
            date_joined=self.now - timedelta(days=self.rng.randint(0, 365 * self.years)),
            **fields,
        )

    def make_teams(self):
        rng, s = self.rng, self.s
        self.dojos = Dojo.objects.bulk_create(
            Dojo(
                id=self.next_id(Dojo),
                name=f"Scale dojo {i}",
                status=Dojo.ACTIVE,
                location=Point(rng.uniform(2.6, 6.3), rng.uniform(49.6, 51.4), srid=4326),
                address=f"Schoolstraat {i}, Belgium",
                tagline="Free coding club for children aged 7 to 17.",
                description="We meet in the library. Bring a laptop if you have one; we have spares. " * 3,
                languages=["nl-be"] if rng.random() < 0.6 else ["fr-be"],
                min_age=7,
                max_age=17,
            )
            for i in range(s.dojos)
        )
        team_size = s.team_per_session + 1
        volunteers = User.objects.bulk_create(
            self.user(
                f"volunteer{i}",
                rng.choice(GIRL_NAMES + BOY_NAMES),
                rng.choice(FAMILY_NAMES),
                background_check_status=User.CHECK_VALIDATED,
                background_check_expires_at=self.now + timedelta(days=200),
            )
            for i in range(s.dojos * team_size)
        )
        Application.objects.bulk_create(
            Application(account=user, kind=Application.MENTOR, status=Application.APPROVED) for user in volunteers
        )
        memberships = []
        for index, dojo in enumerate(self.dojos):
            for place, user in enumerate(volunteers[index * team_size : (index + 1) * team_size]):
                role = DojoMembership.CHAMPION if place == 0 else DojoMembership.MENTOR
                memberships.append(
                    DojoMembership(dojo=dojo, user=user, role=role, status=DojoMembership.ACTIVE, joined_at=self.now)
                )
        DojoMembership.objects.bulk_create(memberships)
        self.teams = {}
        for membership in DojoMembership.objects.all():
            self.teams.setdefault(membership.dojo_id, []).append(membership)
        self.volunteer_ids = [user.id for user in volunteers]
        self.step("dojos", len(self.dojos))
        self.step("volunteers", len(volunteers))

    def make_families(self):
        rng, s = self.rng, self.s
        # Every family that signed up over the years, of which `families` are active now.
        households = s.families + round(s.new_families * (self.years - 1))
        parents = []
        second = []
        for i in range(households):
            family = rng.choice(FAMILY_NAMES)
            parents.append(self.user(f"family{i}", rng.choice(GIRL_NAMES + BOY_NAMES), family))
            if rng.random() < s.guardians_per_child - 1:
                second.append((i, self.user(f"family{i}b", rng.choice(GIRL_NAMES + BOY_NAMES), family)))
        parents = [u for batch in chunks(parents) for u in User.objects.bulk_create(batch)]
        second_users = User.objects.bulk_create([u for _, u in second])
        self.parent_ids = [u.id for u in parents]
        self.guardians = {i: [parents[i].id] for i in range(households)}
        for (i, _), user in zip(second, second_users, strict=True):
            self.guardians[i].append(user.id)

        ninjas, owner = [], []
        for i in range(households):
            dojo = rng.choice(self.dojos)
            for _ in range(2 if rng.random() < s.children_per_family - 1 else 1):
                girl = rng.random() < 0.3
                ninjas.append(
                    Ninja(
                        id=self.next_id(Ninja),
                        name=rng.choice(GIRL_NAMES if girl else BOY_NAMES),
                        family_name=parents[i].last_name,
                        gender="girl" if girl else "boy",
                        date_of_birth=date.today() - timedelta(days=rng.randint(7 * 365, 17 * 365)),
                        home_dojo=dojo,
                        member_since=date.today() - timedelta(days=rng.randint(0, 365 * self.years)),
                    )
                )
                owner.append(i)
        ninjas = [n for batch in chunks(ninjas) for n in Ninja.objects.bulk_create(batch)]
        Guardianship.objects.bulk_create(
            [
                Guardianship(guardian_id=guardian, ninja=ninja, consent_given_at=self.now)
                for ninja, i in zip(ninjas, owner, strict=True)
                for guardian in self.guardians[i]
            ],
            batch_size=BATCH,
        )
        self.ninjas = ninjas
        self.ninja_family = dict(zip((n.id for n in ninjas), owner, strict=True))
        self.by_dojo = {}
        for ninja in ninjas:
            self.by_dojo.setdefault(ninja.home_dojo_id, []).append(ninja)
        self.step("guardian accounts", len(parents) + len(second_users))
        self.step("children", len(ninjas))

    def make_sessions(self):
        rng, s = self.rng, self.s
        events = []
        for dojo in self.dojos:
            count = s.sessions_per_dojo * self.years
            for n in range(count + 2):
                upcoming = n >= count
                day = self.now + (
                    timedelta(days=7 * (n - count + 1))
                    if upcoming
                    else -timedelta(days=rng.randint(1, 365 * self.years))
                )
                start = day.replace(hour=14, minute=0, second=0, microsecond=0)
                events.append(
                    Event(
                        id=self.next_id(Event),
                        name=f"CoderDojo {dojo.name}",
                        dojo=dojo,
                        status=Event.OPEN if upcoming else Event.CLOSED,
                        start_time=start,
                        end_time=start + timedelta(hours=3),
                        places=s.bookings_per_session + 2,
                        venue_name="Public library",
                        description="Scratch, Python and electronics. Bring a laptop if you have one.",
                        published_at=start - timedelta(days=21),
                    )
                )
        self.events = [e for batch in chunks(events) for e in Event.objects.bulk_create(batch)]
        Team = Event.team.through
        Paths = Event.pathways.through
        team_rows, path_rows = [], []
        for event in self.events:
            for membership in rng.sample(self.teams[event.dojo_id], s.team_per_session):
                team_rows.append(Team(event_id=event.id, dojomembership_id=membership.id))
            for pathway in rng.sample(self.pathways, 2):
                path_rows.append(Paths(event_id=event.id, pathway_id=pathway.id))
        Team.objects.bulk_create(team_rows, batch_size=BATCH)
        Paths.objects.bulk_create(path_rows, batch_size=BATCH)
        closed = {e.id for e in self.events if e.status == Event.CLOSED}
        TeamAttendance.objects.bulk_create(
            [
                TeamAttendance(event_id=row.event_id, membership_id=row.dojomembership_id, attended=rng.random() < 0.9)
                for row in team_rows
                if row.event_id in closed
            ],
            batch_size=BATCH,
        )
        self.step("sessions", len(self.events))
        self.step("session team places", len(team_rows))

    def make_bookings(self):
        rng, s = self.rng, self.s
        registrations, cancellations = [], []
        for event in self.events:
            local = self.by_dojo.get(event.dojo_id, [])
            wanted = s.bookings_per_session if event.status == Event.CLOSED else s.bookings_per_session * 7 // 10
            picked = set()
            while len(picked) < wanted + wanted // 10:
                pool = local if local and rng.random() < 0.8 else self.ninjas
                picked.add(rng.choice(pool).id)
            for position, ninja_id in enumerate(picked, start=1):
                waiting = position > event.places
                past = event.status == Event.CLOSED and not waiting
                roll = rng.random()
                registrations.append(
                    Registration(
                        id=self.next_id(Registration),
                        event=event,
                        ninja_id=ninja_id,
                        waiting_list=waiting,
                        position=position,
                        attended=(True if roll < 0.85 else False if roll < 0.95 else None) if past else None,
                        created_at=event.start_time - timedelta(days=rng.randint(1, 20)),
                    )
                )
            for ninja_id in rng.sample(sorted(picked), max(1, len(picked) * 15 // 100)):
                cancellations.append(
                    RegistrationCancellation(
                        ninja_id=ninja_id,
                        event=event,
                        was_waitlisted=False,
                        signed_up_at=event.start_time - timedelta(days=15),
                        cancelled_at=event.start_time - timedelta(days=2),
                        cancelled_by_id=self.parent_ids[self.ninja_family[ninja_id]],
                    )
                )
        self.registrations = [r for batch in chunks(registrations) for r in Registration.objects.bulk_create(batch)]
        RegistrationCancellation.objects.bulk_create(cancellations, batch_size=BATCH)
        Paths = Registration.pathways.through
        Paths.objects.bulk_create(
            [
                Paths(registration_id=r.id, pathway_id=pathway.id)
                for r in self.registrations
                for pathway in rng.sample(self.pathways, 2 if rng.random() < 0.2 else 1)
            ],
            batch_size=BATCH,
        )
        self.step("bookings", len(self.registrations))
        self.step("cancellations", len(cancellations))

    def make_awards(self):
        rng = self.rng
        belts = [Belt.objects.create(name=f"Belt {level}", level=level) for level in range(1, 7)]
        badges = [Badge.objects.create(name=f"Badge {i}", kind=Badge.ONE_OFF) for i in range(1, 16)]
        champion = {dojo_id: team[0] for dojo_id, team in self.teams.items()}
        ninja_badges, ninja_belts = [], []
        for ninja in self.ninjas:
            for badge in rng.sample(badges, rng.choice([0, 1, 1, 2, 3]) * self.years):
                ninja_badges.append(
                    NinjaBadge(
                        ninja=ninja,
                        badge=badge,
                        earned_date=date.today() - timedelta(days=rng.randint(0, 365 * self.years)),
                        awarded_by_id=champion[ninja.home_dojo_id].user_id,
                        awarded_as_membership=champion[ninja.home_dojo_id],
                        note="Finished the Scratch game." if rng.random() < 0.3 else "",
                    )
                )
            if rng.random() < 0.4 * self.years:
                ninja_belts.append(
                    NinjaBelt(
                        ninja=ninja,
                        belt=rng.choice(belts),
                        awarded_on=date.today() - timedelta(days=rng.randint(0, 365 * self.years)),
                        awarded_by_id=champion[ninja.home_dojo_id].user_id,
                        awarded_as_membership=champion[ninja.home_dojo_id],
                        awarded_as_role=DojoMembership.CHAMPION,
                    )
                )
        NinjaBadge.objects.bulk_create(ninja_badges, batch_size=BATCH, ignore_conflicts=True)
        NinjaBelt.objects.bulk_create(ninja_belts, batch_size=BATCH)
        self.step("badges awarded", len(ninja_badges))
        self.step("belts awarded", len(ninja_belts))

    def make_mail(self):
        rng = self.rng
        rendered = {}
        for key, _ in MAIL_TEMPLATES.values():
            for language in ("en-us", "nl-be", "fr-be"):
                rendered[key, language] = render(key, language, SAMPLE_CONTEXT.get(key, {}))
        recipients = self.parent_ids + self.volunteer_ids
        emails = dict(User.objects.filter(id__in=recipients).values_list("id", "email"))
        languages = dict(User.objects.filter(id__in=recipients).values_list("id", "preferred_language"))
        total = 0
        for kind, per_year in capacity.mail_breakdown(self.s).items():
            key, category = MAIL_TEMPLATES[kind]
            rows = []
            for n in range(round(per_year * self.years)):
                user_id = rng.choice(self.parent_ids)
                language = languages[user_id] or "en-us"
                subject, body = rendered[key, language]
                sent = self.now - timedelta(days=rng.randint(0, 365 * self.years), seconds=rng.randint(0, 86400))
                rows.append(
                    EmailMessage(
                        category=category,
                        template_key=key,
                        user_id=user_id,
                        recipient=emails[user_id],
                        language=language,
                        subject=subject,
                        body=body,
                        status=EmailMessage.Status.SENT,
                        priority=5,
                        attempts=1,
                        idempotency_key=f"{key}:{n}:{user_id}",
                        message_id=f"<{uuid.uuid4().hex}@coolregistration.localhost>",
                        claimed_at=sent,
                        sent_at=sent,
                    )
                )
            for batch in chunks(rows):
                EmailMessage.objects.bulk_create(batch)
            total += len(rows)
        # created_at is auto_now_add: spread it over the years like sent_at.
        with connection.cursor() as cursor:
            cursor.execute(f"UPDATE {capacity.MAIL_TABLE} SET created_at = sent_at WHERE sent_at IS NOT NULL")
        self.step("mails", total)

    def make_consents(self):
        rng = self.rng
        optional = [MailCategory.REMINDER, MailCategory.DOJO_NEWS, MailCategory.NEWSLETTER, MailCategory.VOLUNTEER]
        events, preferences = [], []
        for user_id in self.parent_ids:
            for category in [*optional, MailCategory.NEWSLETTER, MailCategory.DOJO_NEWS]:
                events.append(
                    ConsentEvent(
                        user_id=user_id,
                        category=category,
                        subscribed=rng.random() < 0.7,
                        source=ConsentEvent.SIGNUP,
                        wording_version="2026-09-25",
                    )
                )
            for category in rng.sample(optional, 1 if rng.random() < 0.5 else 2):
                preferences.append(MailPreference(user_id=user_id, category=category, subscribed=rng.random() < 0.5))
        ConsentEvent.objects.bulk_create(events, batch_size=BATCH)
        MailPreference.objects.bulk_create(preferences, batch_size=BATCH)
        self.step("consent events", len(events))
        self.step("mail preferences", len(preferences))

    def make_audit_log(self):
        """Entries shaped like the ones auditlog writes for these models."""
        rng = self.rng
        types = {
            m: ContentType.objects.get_for_model(m)
            for m in (Registration, Event, TeamAttendance, User, Ninja, ConsentEvent)
        }
        entries = []

        def add(model, pk, action, changes, actor=None):
            entries.append(
                LogEntry(
                    content_type=types[model],
                    object_pk=str(pk),
                    object_id=pk,
                    object_repr=f"{model.__name__} object ({pk})",
                    action=action,
                    changes=changes,
                    actor_id=actor,
                    timestamp=self.now - timedelta(days=rng.randint(0, 365 * self.years)),
                )
            )

        for r in self.registrations:
            add(
                Registration,
                r.id,
                LogEntry.Action.CREATE,
                {
                    "id": ["None", str(r.id)],
                    "event": ["None", str(r.event_id)],
                    "ninja": ["None", str(r.ninja_id)],
                    "position": ["None", str(r.position)],
                    "created_at": ["None", str(r.created_at)],
                    "waiting_list": ["None", str(r.waiting_list)],
                },
                self.parent_ids[self.ninja_family[r.ninja_id]],
            )
            if r.attended is not None:
                add(
                    Registration,
                    r.id,
                    LogEntry.Action.UPDATE,
                    {"attended": ["None", str(r.attended)]},
                    rng.choice(self.volunteer_ids),
                )
        for event in self.events:
            for _ in range(3):
                add(
                    Event,
                    event.id,
                    LogEntry.Action.UPDATE,
                    {"status": ["draft", "open"], "places": ["20", "22"]},
                    rng.choice(self.volunteer_ids),
                )
            for _ in range(self.s.team_per_session):
                add(
                    TeamAttendance,
                    event.id,
                    LogEntry.Action.CREATE,
                    {"attended": ["None", "True"], "event": ["None", str(event.id)]},
                    rng.choice(self.volunteer_ids),
                )
        user_changes = {
            field: ["None", "x" * 12]
            for field in (
                "id",
                "username",
                "email",
                "first_name",
                "last_name",
                "preferred_language",
                "postal_code",
                "account_type",
                "is_active",
                "date_joined",
                "login_method",
                "title",
                "bio",
            )
        }
        user_changes["password"] = ["***", "***"]
        for user_id in self.parent_ids:
            add(User, user_id, LogEntry.Action.CREATE, user_changes, user_id)
            for _ in range(6):
                add(
                    ConsentEvent,
                    user_id,
                    LogEntry.Action.CREATE,
                    {
                        "id": [None, 1],
                        "user": [None, user_id],
                        "source": [None, "signup"],
                        "category": [None, "newsletter"],
                        "created_at": [None, str(self.now)],
                        "subscribed": [None, True],
                        "wording_version": [None, "2026-09-25"],
                    },
                    user_id,
                )
        for ninja in self.ninjas:
            add(
                Ninja,
                ninja.id,
                LogEntry.Action.CREATE,
                {
                    "id": ["None", str(ninja.id)],
                    "name": ["None", ninja.name],
                    "photo": ["None", ""],
                    "gender": ["None", ninja.gender],
                    "account": ["None", "None"],
                    "home_dojo": ["None", str(ninja.home_dojo_id)],
                    "family_name": ["None", ninja.family_name],
                    "date_of_birth": ["None", str(ninja.date_of_birth)],
                    "allergies_notes": ["***", "***"],
                },
            )
        for batch in chunks(entries):
            LogEntry.objects.bulk_create(batch)
        self.step("audit log entries", len(entries))

    def make_login_sessions(self):
        store = SessionStore()
        sessions = []
        for user_id in self.rng.sample(self.parent_ids, round(self.s.families * 0.3)):
            data = {
                "_auth_user_id": str(user_id),
                "_auth_user_backend": "accounts.backends.EmailOrUsernameBackend",
                "_auth_user_hash": uuid.uuid4().hex * 2,
                "otp_device_id": "",
                "django_language": "nl-be",
            }
            sessions.append(
                Session(
                    session_key=uuid.uuid4().hex,
                    session_data=store.encode(data),
                    expire_date=self.now + timedelta(days=14),
                )
            )
        Session.objects.bulk_create(sessions, batch_size=BATCH)
        self.step("login sessions", len(sessions))
