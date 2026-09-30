"""Load test (CAPACITY.md, "Load tests"): visitors, families and dojo teams
against a production-like run of the site on a `seed_scale` database.

    LOADTEST_DATA=/tmp/loadtest.json locust -f loadtest/locustfile.py --host http://127.0.0.1:8001 \
        --headless -u 200 -r 20 -t 5m --csv /tmp/lt/mixed
    LOADTEST_MODE=rush ...   # only families signing up for the same five sessions at once

The data file comes from loadtest/prepare.py. Every synthetic login's
password is seed_scale's (`LOADTEST_PASSWORD`, default "scale-test")."""

import json
import os
import random

from locust import HttpUser, between, task

DATA = json.load(open(os.environ["LOADTEST_DATA"]))
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "scale-test")
MODE = os.environ.get("LOADTEST_MODE", "mixed")


class SiteUser(HttpUser):
    abstract = True
    wait_time = between(2, 8)

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

    weight = 0 if MODE == "rush" else 3

    def on_start(self):
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

    weight = 0 if MODE == "rush" else 1

    def on_start(self):
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
