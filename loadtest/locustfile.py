"""Load test (CAPACITY.md, "Load tests"): visitors, families and dojo teams.
Usually started through loadtest/run.sh, which also samples /metrics/.

    LOADTEST_DATA=/tmp/loadtest.json locust -f loadtest/locustfile.py \
        --host http://coolregistration.localhost:8001 --headless -u 300 -r 20 -t 3m --csv /tmp/lt/mixed
    LOADTEST_MODE=rush ...     # only families signing up for the same five sessions at once
    LOADTEST_MODE=public ...   # visitors only: no login, no writes (production)
    LOADTEST_CLOSE=1 ...       # a new connection per request, as behind a proxy

`mixed` and `rush` log in and book: they need a `seed_scale` database (the
data file comes from loadtest/prepare.py, every synthetic login's password
is seed_scale's, `LOADTEST_PASSWORD`) and refuse any host that isn't local,
so they can never book real sessions or mail real families. `public` only
reads public pages, finding the sessions on /events/ itself, and is the mode
for production (CAPACITY.md, "Load testing production").

Testing a non-local host anyway (e.g. a demo app deliberately, temporarily
pointed at a throwaway database): set LOADTEST_CONFIRM_REMOTE_HOST to the
exact hostname you're targeting. It must match --host exactly, on purpose —
this is a one-time, explicit confirmation, not a standing setting: if you
copy a working command to test a *different* host later (including the
real one) without changing this, it's refused again."""

import json
import os
import random
import re
from urllib.parse import urlparse

from locust import HttpUser, between, events, task

MODE = os.environ.get("LOADTEST_MODE", "mixed")
if MODE not in ("mixed", "rush", "public"):
    raise SystemExit(f"Unknown LOADTEST_MODE {MODE!r}: mixed, rush or public.")
DATA = json.load(open(os.environ["LOADTEST_DATA"])) if MODE != "public" else {"events": []}
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "scale-test")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "coolregistration.localhost")
CONFIRMED_REMOTE_HOST = os.environ.get("LOADTEST_CONFIRM_REMOTE_HOST", "")


@events.test_start.add_listener
def only_public_beyond_local(environment, **kwargs):
    """The modes that log in and book only run against a local test site,
    or a remote one explicitly confirmed host-by-host (see the docstring)."""
    host = urlparse(environment.host or "").hostname or ""
    if MODE != "public" and host not in LOCAL_HOSTS and host != CONFIRMED_REMOTE_HOST:
        raise SystemExit(
            f"LOADTEST_MODE={MODE} logs in and books sessions: only against a local site, not {host}. "
            f"To confirm {host} is a safe, throwaway target on purpose, set LOADTEST_CONFIRM_REMOTE_HOST={host}."
        )


class SiteUser(HttpUser):
    abstract = True
    wait_time = between(2, 8)

    def on_start(self):
        # LOADTEST_CLOSE=1: a new connection per request, as a proxy that
        # doesn't keep connections to gunicorn open (uvicorn's
        # limit_concurrency counts open connections, not requests).
        if os.environ.get("LOADTEST_CLOSE"):
            self.client.headers["Connection"] = "close"

    def login(self, username):
        self.client.get("/login/", name="/login/")
        response = self.client.post(
            "/login/",
            data={
                "csrfmiddlewaretoken": self.client.cookies.get("csrftoken", ""),
                "login_view-current_step": "auth",
                "auth-username": username,
                "auth-password": PASSWORD,
            },
            name="/login/ [POST]",
            allow_redirects=False,
        )
        if response.status_code != 302:
            response.failure = True
            raise RuntimeError(f"login failed for {username}: {response.status_code}")

    def post(self, url, data, name, **kwargs):
        data = {"csrfmiddlewaretoken": self.client.cookies.get("csrftoken", ""), **data}
        return self.client.post(url, data=data, name=name, **kwargs)


class Visitor(SiteUser):
    """Someone looking around without logging in."""

    weight = 0 if MODE == "rush" else 6

    @task(3)
    def home(self):
        self.client.get("/", name="/")

    @task(2)
    def events(self):
        self.client.get("/events/", name="/events/")

    def on_start(self):
        super().on_start()
        if not DATA["events"]:
            # public mode: the sessions the site itself lists.
            page = self.client.get("/events/", name="/events/").text
            DATA["events"] = sorted({int(n) for n in re.findall(r'href="/events/(\d+)/"', page)}) or [0]

    @task(3)
    def event(self):
        self.client.get(f"/events/{random.choice(DATA['events'])}/", name="/events/<id>/")

    @task(2)
    def dojos(self):
        self.client.get("/dojos/", name="/dojos/")

    @task(1)
    def upcoming_widget(self):
        self.client.get("/events/upcoming-sessions-widget/?page=2", name="/events/upcoming-sessions-widget/")


class Family(SiteUser):
    """A parent who logs in, looks at their page and books sessions."""

    weight = 3 if MODE == "mixed" else 0

    def on_start(self):
        super().on_start()
        self.family = random.choice(DATA["families"])
        self.login(self.family["username"])

    @task(3)
    def account(self):
        self.client.get("/account/", name="/account/")

    @task(2)
    def mail_preferences(self):
        self.client.get("/account/mail/", name="/account/mail/")

    @task(2)
    def book(self):
        if not self.family["events"]:
            return
        event = random.choice(self.family["events"])
        self.client.get(f"/events/{event}/signup/", name="/events/<id>/signup/")
        self.post(
            f"/events/{event}/signup/",
            {"child": self.family["children"][:1]},
            name="/events/<id>/signup/ [POST]",
        )


class RushFamily(SiteUser):
    """Registrations open for a popular session: every family signs up
    straight away (LOADTEST_MODE=rush)."""

    weight = 1 if MODE == "rush" else 0
    wait_time = between(0.5, 2)

    def on_start(self):
        super().on_start()
        self.family = random.choice(DATA["families"])
        self.login(self.family["username"])
        self.event = random.choice(DATA["rush"])

    @task
    def rush(self):
        self.client.get(f"/events/{self.event}/signup/", name="rush: signup page")
        self.post(
            f"/events/{self.event}/signup/",
            {"child": self.family["children"]},
            name="rush: signup [POST]",
        )
        self.client.get(f"/events/{self.event}/", name="rush: event page")


class DojoTeam(SiteUser):
    """A champion taking attendance during a session."""

    weight = 1 if MODE == "mixed" else 0

    def on_start(self):
        super().on_start()
        self.member = random.choice(DATA["team"])
        self.login(self.member["username"])
        self.base = f"/dojos/{self.member['dojo']}/events/{self.member['event']}/attendance/"

    @task(1)
    def dashboard(self):
        self.client.get(f"/dojos/{self.member['dojo']}/dashboard/", name="/dojos/<id>/dashboard/")

    @task(2)
    def attendance(self):
        self.client.get(self.base, name="/dojos/<id>/events/<id>/attendance/")

    @task(4)
    def mark(self):
        if not self.member["registrations"]:
            return
        registration = random.choice(self.member["registrations"])
        self.post(
            f"{self.base}{registration}/",
            {"attended": random.choice(["present", "absent"])},
            name="/dojos/<id>/events/<id>/attendance/<id>/ [POST]",
            headers={"HX-Request": "true"},
        )
