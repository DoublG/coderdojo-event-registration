"""Memory per function of the site (MEMORY.md): serves every page and runs
every background job once on a `seed_scale` database, and records for each
of the site's own functions how much memory a call takes.

    DB_NAME=test_memory REDIS_CACHE_DB=4 REDIS_CHANNELS_DB=5 CELERY_BROKER_DB=6 \\
        python quality/memory_profile.py > quality/results/memory-$(date +%F).json

It writes to that database (bookings, attendance, a campaign's mail, the
retention job, one account deleted), so it refuses any database whose name
doesn't start with `test_`.

How it measures: tracemalloc counts every Python allocation, and
sys.monitoring (Python 3.12+) reports each start, return, yield and unwind of
a function in the site's own code (the apps and website/; not tests,
migrations, seeders or commands; everything else is switched off per code
object, so Django itself runs at full speed). At each of those events the
peak since the previous event is read and reset, and charged to the function
on top of the stack; a function's peak is passed on to its caller when it
returns. Per call that gives:

- peak: the most memory above what was in use when the call started, at any
  moment during it, including everything it called;
- own peak: the same, but leaving out the moments when another function of
  the site that it called was running (what that function returned still
  counts): high here and the allocation is in this function's own body or
  the library calls it makes (Django's ORM, templates);
- kept: what was still allocated once it had returned (its return value and
  anything it cached or left behind). Read at the next event, since at the
  return event itself the function's local variables are still alive; so it
  can include a little of what the caller did in between.

Only Python allocations count (C libraries' own buffers don't, nor memory
the allocator keeps after a free), so a process's RSS is higher; and the
data decides the figures, so they hold for the size of the database used.

Before measuring it serves every page once untraced, so imports and the
template cache are warm; then it empties the data cache, so every cached
part of a page is built once while measured."""

import contextlib
import importlib
import json
import os
import pkgutil
import sys
import threading
import time
import tracemalloc
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "website.settings")
# Production's settings: with DEBUG on, Django keeps every SQL statement in
# memory (and silk records every request), which would be charged to the
# functions that run them.
os.environ.update(DEBUG="false", SILK="false", METRICS_ENABLED="false", EMAIL_HOST="", METRICS_TOKEN="memory-profile")  # noqa: S106 (a throwaway token for /metrics/ on a test database)

SITE_APPS = (
    "accounts",
    "api",
    "applications",
    "campaigns",
    "content",
    "core",
    "dojos",
    "events",
    "geo",
    "mailing",
    "monitoring",
    "notifications",
    "pages",
    "pathways",
    "privacy",
    "website",
)
NOT_SITE = ("tests", "testing", "migrations", "management", "seed_", "seeding", "seed_templates", "seed_translations")
HOST = "coolregistration.localhost"


def is_site(filename):
    """The site's production code (CODING_STANDARDS.md, "Production code and
    development-only code"), by file name."""
    try:
        relative = Path(filename).resolve().relative_to(ROOT)
    except ValueError:
        return False
    parts = relative.parts
    if len(parts) < 2 or parts[0] not in SITE_APPS or relative.suffix != ".py":
        return False
    return not any(part.startswith(NOT_SITE) for part in parts[1:])


class Frame:
    __slots__ = ("key", "start", "peak", "own", "is_call")

    def __init__(self, key, start, is_call):
        self.key, self.start, self.peak, self.own, self.is_call = key, start, start, start, is_call


class Stats:
    __slots__ = ("calls", "peak", "peak_total", "own", "kept", "kept_total", "worst_step")

    def __init__(self):
        self.calls = self.peak = self.peak_total = self.own = self.kept = self.kept_total = 0
        self.worst_step = ""


class MemoryTracer:
    """Peak, own peak and kept memory per call of the site's functions, and
    per labelled step of the workload."""

    EVENTS = ("PY_START", "PY_RESUME", "PY_THROW", "PY_RETURN", "PY_YIELD", "PY_UNWIND")

    def __init__(self):
        self.mon = sys.monitoring
        # A tool id no profiler or debugger claims (0-2 and 5 are named).
        self.tool = next(i for i in (3, 4) if self.mon.get_tool(i) is None)
        self.wanted = {}
        self.stack = []
        self.stats = defaultdict(Stats)
        self.steps = []
        self.step = ""
        self.pending = []  # (stats, start) of calls whose kept memory is read at the next event
        self.thread = threading.get_ident()

    def start(self):
        tracemalloc.start(1)
        mon, events = self.mon, self.mon.events
        mon.use_tool_id(self.tool, "memory_profile")
        for event, callback in (
            ("PY_START", self._start),
            ("PY_RESUME", self._resume),
            ("PY_THROW", self._resume),
            ("PY_RETURN", self._leave),
            ("PY_YIELD", self._leave),
            ("PY_UNWIND", self._unwind),
        ):
            mon.register_callback(self.tool, getattr(events, event), callback)
        mask = 0
        for event in self.EVENTS:
            mask |= getattr(events, event)
        mon.set_events(self.tool, mask)

    def stop(self):
        self.mon.set_events(self.tool, 0)
        for event in self.EVENTS:
            self.mon.register_callback(self.tool, getattr(self.mon.events, event), None)
        self.mon.free_tool_id(self.tool)
        tracemalloc.stop()

    def _want(self, code):
        want = self.wanted.get(code)
        if want is None:
            want = self.wanted[code] = is_site(code.co_filename)
        return want and threading.get_ident() == self.thread

    def _sample(self):
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        self._settle(current)
        if self.stack:
            top = self.stack[-1]
            top.peak = max(top.peak, peak)
            top.own = max(top.own, peak)
        return current

    def _settle(self, current):
        for stats, start in self.pending:
            stats.kept = max(stats.kept, current - start)
            stats.kept_total += current - start
        self.pending.clear()

    def _push(self, key, is_call):
        self.stack.append(Frame(key, self._sample(), is_call))

    def _pop(self, key):
        self._sample()
        while self.stack:
            frame = self.stack.pop()
            self._record(frame)
            if frame.key is key or not self.stack:
                return

    def _record(self, frame):
        if self.stack:
            self.stack[-1].peak = max(self.stack[-1].peak, frame.peak)
        if isinstance(frame.key, str):
            return
        stats = self.stats[frame.key]
        peak = frame.peak - frame.start
        self.pending.append((stats, frame.start))
        if frame.is_call:
            stats.calls += 1
        if peak > stats.peak:
            stats.peak, stats.worst_step = peak, self.step
        stats.peak_total += peak
        stats.own = max(stats.own, frame.own - frame.start)

    def _start(self, code, offset):
        if code not in self.wanted and not is_site(code.co_filename):
            self.wanted[code] = False
            return self.mon.DISABLE
        if self._want(code):
            self._push(code, True)

    def _resume(self, code, offset, *exc):
        if self._want(code):
            self._push(code, False)

    def _leave(self, code, offset, value):
        if self._want(code):
            self._pop(code)

    def _unwind(self, code, offset, exc):
        if self._want(code):
            self._pop(code)

    @contextlib.contextmanager
    def measure(self, kind, label, **extra):
        """One step of the workload: its peak and kept memory, and the label
        the functions it runs are charged to."""
        self.step = label
        frame = Frame(label, 0, False)
        frame.start = frame.peak = frame.own = self._sample()
        self.stack.append(frame)
        began = time.perf_counter()
        row = {"kind": kind, "label": label, **extra}
        try:
            yield row
        except Exception as error:  # a step that breaks is reported, not fatal
            row["error"] = f"{type(error).__name__}: {error}"[:300]
        finally:
            current = self._sample()
            while self.stack and self.stack[-1] is not frame:
                self._record(self.stack.pop())
            self.stack.remove(frame)
            self._settle(current)
            row["peak"] = frame.peak - frame.start
            row["kept"] = current - frame.start
            row["seconds"] = round(time.perf_counter() - began, 2)
            self.steps.append(row)
            self.step = ""

    def functions(self):
        rows = []
        for code, s in self.stats.items():
            if not s.calls:
                continue
            path = str(Path(code.co_filename).resolve().relative_to(ROOT))
            rows.append(
                {
                    "name": code.co_qualname,
                    "path": path,
                    "line": code.co_firstlineno,
                    "calls": s.calls,
                    "peak": s.peak,
                    "peak_mean": round(s.peak_total / s.calls),
                    "own": s.own,
                    "kept": s.kept,
                    "kept_total": s.kept_total,
                    "worst_step": s.worst_step,
                }
            )
        return sorted(rows, key=lambda r: -r["peak"])


def import_site():
    """Every module of the site, so first imports aren't measured as a
    function's memory."""
    for app in SITE_APPS:
        package = importlib.import_module(app)
        for module in pkgutil.walk_packages(package.__path__, f"{app}."):
            if is_site(ROOT / (module.name.replace(".", "/") + ".py")) or module.ispkg:
                if not any(part.startswith(NOT_SITE) for part in module.name.split(".")[1:]):
                    with contextlib.suppress(Exception):
                        importlib.import_module(module.name)


class Workload:
    """What the site does, on the scale database: every page as the persona
    that may open it, the writes families and teams make most, and every
    background job."""

    def __init__(self, tracer):
        import django.test.client
        from django.test import Client

        # The test client keeps a copy of every template context it renders
        # (for response.context): memory a real request never holds.
        django.test.client.store_rendered_templates = lambda *args, **kwargs: None

        self.tracer = tracer
        self.client_class = Client
        self.people = self.prepare_people()
        self.values = self.prepare_values()

    def prepare_people(self):
        from accounts.admin_access import AdminAccessError
        from accounts.models import Guardianship, OrganisationRole, User
        from accounts.testing import with_admin_access
        from dojos.models import DojoMembership

        champion = (
            DojoMembership.objects.filter(role=DojoMembership.CHAMPION, status=DojoMembership.ACTIVE)
            .select_related("user", "dojo")
            .order_by("dojo_id")
            .first()
        )
        # The family with the most children at that dojo: the account page's worst case.
        family = (
            Guardianship.objects.filter(ninja__home_dojo=champion.dojo).values("guardian").order_by("guardian").first()
        )
        family = User.objects.get(pk=family["guardian"])
        admin, _ = User.objects.get_or_create(
            username="memory-profile-admin",
            defaults={"email": "memory-profile-admin@scale.example", "first_name": "Memory", "last_name": "Admin"},
        )
        for role in (OrganisationRole.ADMIN, OrganisationRole.REVIEWER):
            OrganisationRole.objects.get_or_create(account=admin, role=role)
        admin.is_superuser = True  # every area and the Django admin's own pages
        admin.save(update_fields=["is_superuser"])
        with contextlib.suppress(AdminAccessError):  # still open from an earlier run
            with_admin_access(admin)
        return {"anonymous": None, "family": family, "champion": champion.user, "organisation": admin}

    def prepare_values(self):
        """A sample value for every URL parameter, from the champion's dojo
        and the family where it matters."""
        from accounts.models import Ninja
        from api.models import DojoApiClient
        from applications.models import Application
        from campaigns.models import Campaign, Journey, Segment, SegmentGroup, SegmentRule
        from content.models import Announcement, Promotion, Sponsor
        from dojos.models import DojoMembership
        from events.models import Badge, Event, Registration
        from mailing.models import EmailTemplate
        from notifications.models import Notification
        from pathways.models import Pathway

        champion = self.people["champion"]
        membership = DojoMembership.objects.filter(user=champion, role=DojoMembership.CHAMPION).first()
        dojo = membership.dojo
        past = Event.objects.filter(dojo=dojo, status=Event.CLOSED).order_by("-start_time").first()
        child = Ninja.objects.of_guardian(self.people["family"]).first()

        def first(queryset):
            row = queryset.order_by("pk").values_list("pk", flat=True).first()
            return row if row is not None else 0

        template = EmailTemplate.objects.order_by("pk").first()
        return {
            "dojo_id": dojo.pk,
            "event_id": past.pk,
            "registration_id": first(Registration.objects.filter(event=past)),
            "ninja_id": child.pk,
            "member_id": first(DojoMembership.objects.filter(dojo=dojo).exclude(pk=membership.pk)),
            "membership_id": first(DojoMembership.objects.filter(dojo=dojo).exclude(pk=membership.pk)),
            "announcement_id": first(Announcement.objects.filter(dojo=dojo)),
            "application_id": first(Application.objects.all()),
            "badge_id": first(Badge.objects.all()),
            "campaign_id": first(Campaign.objects.filter(dojo__isnull=True)),
            "client_id": first(DojoApiClient.objects.all()),
            "journey_id": first(Journey.objects.all()),
            "segment_id": first(Segment.objects.all()),
            "group_id": first(SegmentGroup.objects.all()),
            "rule_id": first(SegmentRule.objects.all()),
            "notification_id": first(Notification.objects.all()),
            "pathway_id": first(Pathway.objects.all()),
            "promotion_id": first(Promotion.objects.all()),
            "sponsor_id": first(Sponsor.objects.all()),
            "user_id": self.people["family"].pk,
            "key": template.key if template else "",
            "language": "en-us",
            "kind": "awards",
            "dojo_mailing": first(Campaign.objects.filter(dojo=dojo)),
        }

    def client(self, persona):
        if persona == "api":
            return self.api_client()
        client = self.client_class(HTTP_HOST=HOST, secure=True, headers={"authorization": "Bearer memory-profile"})
        if self.people[persona] is not None:
            client.force_login(self.people[persona])
        return client

    def api_client(self):
        """A dojo app's client with both scopes and a token, the way an app
        gets one (api.services, the client credentials grant)."""
        import base64

        from api import services
        from dojos.models import Dojo

        dojo = Dojo.objects.get(pk=self.values["dojo_id"])
        if not hasattr(self, "_api"):
            _, client_id, secret = services.create_client(
                dojo, "Memory profile", ["attendance:read", "attendance:write"], self.people["champion"]
            )
            basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
            response = self.client_class(HTTP_HOST=HOST, secure=True).post(
                "/api/oauth/token/", {"grant_type": "client_credentials"}, headers={"authorization": f"Basic {basic}"}
            )
            self._api = response.json()["access_token"]
        return self.client_class(HTTP_HOST=HOST, secure=True, headers={"authorization": f"Bearer {self._api}"})

    def pages(self):
        """(persona, url) for every GET-able route of the site whose
        parameters have a sample value; the URL's prefix decides who opens it."""
        import re

        from django.urls import get_resolver
        from django.urls.resolvers import URLResolver

        routes = []

        def walk(patterns, prefix=""):
            for pattern in patterns:
                if isinstance(pattern, URLResolver):
                    walk(pattern.url_patterns, prefix + str(pattern.pattern))
                else:
                    routes.append((prefix + str(pattern.pattern), pattern.name))

        walk(get_resolver().url_patterns)
        seen, out = set(), []
        for route, name in routes:
            if route.startswith(("admin", "__debug__", "silk", "static", "media", "ws/", "api/oauth")):
                continue
            if route.startswith("^") or "(?P" in route:
                continue
            params = re.findall(r"<(?:\w+:)?(\w+)>", route)
            if any(param not in self.values for param in params):
                continue
            values = (
                dict(self.values, campaign_id=self.values["dojo_mailing"])
                if route.startswith("dojos/")
                else self.values
            )
            url = "/" + re.sub(r"<(?:\w+:)?(\w+)>", lambda m, values=values: str(values[m.group(1)]), route)
            url = url.replace("$", "")
            if url in seen:
                continue
            seen.add(url)
            if route.startswith("api/"):
                persona = "api"
            elif route.startswith("manage/"):
                persona = "organisation"
            elif route.startswith("dojos/") and params:
                persona = "champion"
            elif route.startswith(("account/", "events/", "mail/", "notifications/")):
                persona = "family"
            else:
                persona = "anonymous"
            out.append((persona, url, name))
        # Public pages logged in as a family too: the navigation is built per account.
        for url in ("/", "/dojos/", "/events/"):
            out.append(("family", url, "logged in"))
        return out

    def visit_pages(self, measured):
        clients = {persona: self.client(persona) for persona in (*self.people, "api")}
        for persona, url, name in self.pages():
            if not measured:
                with contextlib.suppress(Exception):
                    clients[persona].get(url)
                continue
            with self.tracer.measure("page", f"GET {url}", persona=persona, route=name) as row:
                response = clients[persona].get(url)
                row["status"] = response.status_code
                row["bytes"] = len(getattr(response, "content", b"") or b"")
                del response  # what the page keeps, not the client's copy of the response

    def writes(self):
        """The writes that happen most: a family booking and cancelling, a
        team marking attendance, posting an update."""
        from events import registrations
        from events.models import Event

        family = self.people["family"]
        champion = self.client("champion")
        values = self.values
        from accounts.models import Ninja

        children = list(Ninja.objects.of_guardian(family))
        free = (
            Event.objects.visible()
            .filter(status=Event.OPEN)
            .exclude(registration__ninja__in=children)
            .order_by("start_time")[:2]
        )
        if len(free) == 2:
            results = []
            with self.tracer.measure("write", "Sign up a family's children (events.registrations.sign_up)"):
                results = registrations.sign_up(free[0], children)
            with self.tracer.measure("write", "Cancel those places (events.registrations.cancel)"):
                for result in results:
                    registrations.cancel(result["registration"], family)
            with self.tracer.measure("write", "POST event sign-up (page)") as row:
                response = self.client("family").post(
                    f"/events/{free[1].pk}/signup/", {"child": [c.pk for c in children]}
                )
                row["status"] = response.status_code
        base = f"/dojos/{values['dojo_id']}/events/{values['event_id']}/attendance"
        with self.tracer.measure("write", "POST mark all present (page)") as row:
            row["status"] = champion.post(f"{base}/mark-all/", HTTP_HX_REQUEST="true").status_code
        with self.tracer.measure("write", "POST mark one child present (page)") as row:
            row["status"] = champion.post(
                f"{base}/{values['registration_id']}/", {"attended": "present"}, HTTP_HX_REQUEST="true"
            ).status_code

    def segments_and_campaigns(self):
        from campaigns import services
        from campaigns.models import Campaign, Segment
        from campaigns.segmentation.resolver import SegmentResolver
        from mailing.models import EmailMessage

        for segment in Segment.objects.order_by("pk"):
            with self.tracer.measure("segment", f"Resolve segment “{segment.name}”") as row:
                row["accounts"] = SegmentResolver().resolve(segment).count()
        campaign = Campaign.objects.filter(dojo__isnull=True, status=Campaign.Status.DRAFT).order_by("pk").first()
        if campaign:
            admin = self.people["organisation"]
            with self.tracer.measure("campaign", f"Launch and queue campaign “{campaign.name}”") as row:
                services.launch(campaign, admin)
                services.queue_mail(campaign.pk)
                row["mails"] = EmailMessage.objects.filter(campaign=campaign).count()

    def jobs(self):
        """Every beat job, the way beat starts it (Celery runs eagerly here,
        so what a job hands to the queue runs inside it)."""
        from django.conf import settings

        from website.celery import app

        names = sorted({entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()})
        destructive = {"privacy.tasks.apply_retention"}
        for name in [n for n in names if n not in destructive] + sorted(destructive & set(names)):
            task = app.tasks.get(name)
            if task is None:
                continue
            with self.tracer.measure("job", name):
                task.apply()
                # apply() swallows a task's exception into its result.
        # Twice the mail dispatcher: the campaign queued thousands of mails.
        task = app.tasks["mailing.tasks.send_pending_emails"]
        for _ in range(2):
            with self.tracer.measure("job", "mailing.tasks.send_pending_emails (after the campaign)"):
                task.apply()

    def privacy(self):
        from privacy import deletion
        from privacy.export import export_person

        family = self.people["family"]
        with self.tracer.measure("privacy", "Export a family's data (export_person)"):
            export_person(family)
        with self.tracer.measure("privacy", "Delete a family's account (privacy.deletion)"):
            deletion.delete_account(family, requested_by=self.people["organisation"])


def database_size():
    from accounts.models import Ninja, User
    from dojos.models import Dojo
    from events.models import Event, Registration
    from mailing.models import EmailMessage

    return {
        "dojos": Dojo.objects.count(),
        "accounts": User.objects.count(),
        "children": Ninja.objects.count(),
        "sessions": Event.objects.count(),
        "registrations": Registration.objects.count(),
        "mails": EmailMessage.objects.count(),
    }


def main():
    import django

    django.setup()
    from django.conf import settings
    from django.core.cache import cache

    if not settings.DATABASES["default"]["NAME"].startswith("test_"):
        sys.exit("memory_profile.py writes to its database: only on a test_ database (DB_NAME=test_memory).")
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    from website.celery import app

    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = False

    import_site()
    size = database_size()
    tracer = MemoryTracer()
    workload = Workload(tracer)
    print("warming up", file=sys.stderr)
    workload.visit_pages(measured=False)
    cache.clear()
    tracer.start()
    try:
        print("pages", file=sys.stderr)
        workload.visit_pages(measured=True)
        print("writes", file=sys.stderr)
        workload.writes()
        print("segments and campaigns", file=sys.stderr)
        workload.segments_and_campaigns()
        print("jobs", file=sys.stderr)
        workload.jobs()
        print("privacy", file=sys.stderr)
        workload.privacy()
    finally:
        tracer.stop()
    json.dump(
        {
            "date": date.today().isoformat(),
            "python": sys.version.split()[0],
            "database": size,
            "steps": tracer.steps,
            "functions": tracer.functions(),
        },
        sys.stdout,
        indent=1,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
