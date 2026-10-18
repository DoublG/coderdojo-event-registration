import base64
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from dojos.models import DojoMembership
from dojos.testing import add_member, make_champion, make_dojo, make_mentor
from events.models import Event, Registration, TeamAttendance

from . import services
from .models import DojoApiClient


def _basic(client_id, secret):
    return "Basic " + base64.b64encode(f"{client_id}:{secret}".encode()).decode()


class ApiTestCase(TestCase):
    def setUp(self):
        self.champion = make_champion(username="chris", email="chris@example.com", first_name="Chris")
        self.dojo = make_dojo("Ghent", champion=self.champion)
        self.mentor = make_mentor(username="mia", email="mia@example.com", first_name="Mia")
        self.mentor_membership = add_member(self.dojo, self.mentor)
        start = timezone.now() + timedelta(days=2)
        self.event = Event.objects.create(
            name="Scratch",
            dojo=self.dojo,
            status=Event.OPEN,
            places=10,
            start_time=start,
            end_time=start + timedelta(hours=2),
        )
        self.event.team.add(self.mentor_membership)
        parent = User.objects.create(username="an", email="an@example.com")
        self.kid = Ninja.objects.create(name="Lotte", allergies_notes="Peanuts")
        Guardianship.objects.create(guardian=parent, ninja=self.kid)
        self.registration = Registration.objects.create(
            event=self.event, ninja=self.kid, waiting_list=False, position=1
        )
        waiting = Ninja.objects.create(name="Waiting Kid")
        Registration.objects.create(event=self.event, ninja=waiting, waiting_list=True, position=2)

    def make_client(self, scopes=(DojoApiClient.READ, DojoApiClient.WRITE), dojo=None):
        return services.create_client(dojo or self.dojo, "Scan app", list(scopes), self.champion)

    def token(self, client_id, secret, **data):
        return self.client.post(
            reverse("oauth2_token"),
            {"grant_type": "client_credentials", **data},
            HTTP_AUTHORIZATION=_basic(client_id, secret),
        )

    def bearer(self, scopes=(DojoApiClient.READ, DojoApiClient.WRITE)):
        client, client_id, secret = self.make_client(scopes)
        response = self.token(client_id, secret)
        self.assertEqual(response.status_code, 200, response.content)
        return client, {"HTTP_AUTHORIZATION": f"Bearer {response.json()['access_token']}"}


class ClientPageTests(ApiTestCase):
    """The dojo's API page: the champion only."""

    def test_only_the_champion(self):
        url = reverse("dojo_api_clients", args=[self.dojo.id])
        self.client.force_login(self.mentor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(User.objects.create(username="nobody"))
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.champion)
        self.assertTemplateUsed(self.client.get(url), "api/dojo_api_clients.html")

    def test_the_sidebar_link_is_for_the_champion(self):
        url = reverse("dojo_api_clients", args=[self.dojo.id])
        self.client.force_login(self.champion)
        self.assertContains(self.client.get(reverse("dojo_dashboard", args=[self.dojo.id])), url)
        self.client.force_login(self.mentor)
        self.assertNotContains(self.client.get(reverse("dojo_dashboard", args=[self.dojo.id])), url)

    def test_adding_a_client_shows_its_secret_once(self):
        self.client.force_login(self.champion)
        url = reverse("dojo_api_clients", args=[self.dojo.id])
        response = self.client.post(url, {"name": "Scan app", "scope": [DojoApiClient.READ]})
        self.assertContains(response, "See the sessions and who has a place")
        secret = response.context["new_secret"]
        self.assertContains(response, secret)
        client = DojoApiClient.objects.get()
        self.assertEqual(
            (client.name, client.scopes, client.created_by), ("Scan app", [DojoApiClient.READ], self.champion)
        )
        self.assertTrue(client.account.is_service)
        self.assertFalse(client.account.has_usable_password())
        self.assertNotEqual(client.application.client_secret, secret)  # stored hashed
        self.assertNotContains(self.client.get(url), secret)

    def test_the_developer_addresses_use_the_sites_address(self):
        from django.conf import settings

        self.client.force_login(self.champion)
        response = self.client.get(reverse("dojo_api_clients", args=[self.dojo.id]))
        self.assertContains(response, settings.SITE_URL + reverse("oauth2_token"))
        self.assertContains(response, settings.SITE_URL + reverse("api-v1:openapi-view"))

    def test_a_client_needs_a_name_and_a_scope(self):
        self.client.force_login(self.champion)
        response = self.client.post(reverse("dojo_api_clients", args=[self.dojo.id]), {"name": "Scan app"})
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertFalse(DojoApiClient.objects.exists())

    def test_new_secret(self):
        client, client_id, secret = self.make_client()
        self.client.force_login(self.champion)
        response = self.client.post(reverse("dojo_api_client_renew", args=[self.dojo.id, client.id]))
        new_secret = response.context["new_secret"]
        self.assertEqual(self.token(client_id, secret).status_code, 401)
        self.assertEqual(self.token(client_id, new_secret).status_code, 200)

    def test_delete_stops_the_client_and_keeps_its_account(self):
        from oauth2_provider.models import Application

        client, client_id, secret = self.make_client()
        account = client.account
        self.client.force_login(self.champion)
        response = self.client.post(reverse("dojo_api_client_delete", args=[self.dojo.id, client.id]))
        self.assertRedirects(response, reverse("dojo_api_clients", args=[self.dojo.id]))
        self.assertFalse(DojoApiClient.objects.filter(pk=client.pk).exists())
        self.assertFalse(Application.objects.filter(client_id=client_id).exists())
        self.assertEqual(self.token(client_id, secret).status_code, 401)
        account.refresh_from_db()
        self.assertFalse(account.is_active)

    def test_delete_is_for_the_champion_only(self):
        client, _id, _secret = self.make_client()
        self.client.force_login(self.mentor)
        response = self.client.post(reverse("dojo_api_client_delete", args=[self.dojo.id, client.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(DojoApiClient.objects.filter(pk=client.pk).exists())

    def test_another_dojos_client_is_out_of_reach(self):
        other_champion = make_champion(username="olga")
        other = make_dojo("Leuven", champion=other_champion)
        client, _id, _secret = self.make_client(dojo=other)
        self.client.force_login(self.champion)
        response = self.client.post(reverse("dojo_api_client_delete", args=[self.dojo.id, client.id]))
        self.assertEqual(response.status_code, 404)


class TokenTests(ApiTestCase):
    def test_client_credentials_give_a_token_with_the_clients_scopes(self):
        _client, client_id, secret = self.make_client([DojoApiClient.READ])
        response = self.token(client_id, secret)
        self.assertEqual(response.json()["scope"], DojoApiClient.READ)
        self.assertEqual(response.json()["expires_in"], 3600)

    def test_no_scope_beyond_what_the_champion_allowed(self):
        _client, client_id, secret = self.make_client([DojoApiClient.READ])
        self.assertEqual(self.token(client_id, secret, scope=DojoApiClient.WRITE).status_code, 400)

    def test_credentials_as_form_fields(self):
        """What OAuth tools such as the reference page's Authorize button may send."""
        _client, client_id, secret = self.make_client()
        response = self.client.post(
            reverse("oauth2_token"),
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": secret,
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_wrong_secret(self):
        _client, client_id, _secret = self.make_client()
        self.assertEqual(self.token(client_id, "nope").status_code, 401)

    def test_only_a_hash_of_the_token_is_stored(self):
        """RFC 9700 token storage (settings.OAUTH2_PROVIDER): the database never holds a usable token."""
        from oauth2_provider.models import AccessToken

        _client, headers = self.bearer()
        stored = AccessToken.objects.get()
        self.assertEqual(stored.token, "")
        self.assertTrue(stored.token_checksum)
        self.assertEqual(self.client.get("/api/v1/events", **headers).status_code, 200)

    def test_no_password_grant(self):
        _client, client_id, secret = self.make_client()
        response = self.token(client_id, secret, username=self.champion.username, password="whatever")
        self.assertEqual(response.status_code, 200)  # still client credentials: the grant_type decides
        response = self.client.post(
            reverse("oauth2_token"),
            {"grant_type": "password", "username": self.champion.username, "password": "whatever"},
            HTTP_AUTHORIZATION=_basic(client_id, secret),
        )
        self.assertEqual(response.status_code, 400)

    def test_a_token_in_the_url_is_not_accepted(self):
        _client, headers = self.bearer()
        token = headers["HTTP_AUTHORIZATION"].removeprefix("Bearer ")
        self.assertEqual(self.client.get(f"/api/v1/events?access_token={token}").status_code, 401)


class AttendanceApiTests(ApiTestCase):
    def test_no_token(self):
        self.assertEqual(self.client.get("/api/v1/events").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/events", HTTP_AUTHORIZATION="Bearer nope").status_code, 401)

    def test_the_dojos_upcoming_events(self):
        _client, auth = self.bearer()
        other = make_dojo("Leuven", champion=make_champion(username="olga"))
        Event.objects.create(
            name="Elsewhere", dojo=other, places=5, start_time=self.event.start_time, end_time=self.event.end_time
        )
        response = self.client.get("/api/v1/events", **auth)
        self.assertEqual([e["name"] for e in response.json()], ["Scratch"])
        self.assertEqual(self.client.get("/api/v1/events?when=past", **auth).json(), [])

    def test_attendance_lists_confirmed_children_and_the_team_without_health_notes(self):
        _client, auth = self.bearer([DojoApiClient.READ])
        data = self.client.get(f"/api/v1/events/{self.event.id}/attendance", **auth).json()
        self.assertEqual(
            data["children"],
            [{"registration_id": self.registration.id, "name": "Lotte", "attended": None, "answers": []}],
        )
        self.assertEqual(data["questions"], [])
        self.assertEqual([m["membership_id"] for m in data["team"]], [self.mentor_membership.id])
        self.assertNotIn("Peanuts", str(data))

    def test_attendance_has_the_sign_up_questions_and_answers(self):
        _client, auth = self.bearer([DojoApiClient.READ])
        laptop = self.event.questions.create(text="Own laptop?", position=1)
        lunch = self.event.questions.create(text="Lunch?", position=2)
        self.registration.answers.create(question=laptop, answer=False)
        data = self.client.get(f"/api/v1/events/{self.event.id}/attendance", **auth).json()
        self.assertEqual(
            data["questions"], [{"id": laptop.id, "text": "Own laptop?"}, {"id": lunch.id, "text": "Lunch?"}]
        )
        self.assertEqual(data["children"][0]["answers"], [{"question_id": laptop.id, "answer": False}])

    def test_correcting_an_answer_as_the_client(self):
        from auditlog.models import LogEntry

        client, auth = self.bearer()
        laptop = self.event.questions.create(text="Own laptop?", position=1)
        url = f"/api/v1/events/{self.event.id}/attendance/children/{self.registration.id}/answers/{laptop.id}"
        response = self.client.put(url, {"answer": True}, content_type="application/json", **auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answers"], [{"question_id": laptop.id, "answer": True}])
        answer = self.registration.answers.get()
        self.assertEqual(LogEntry.objects.get_for_object(answer).get().actor, client.account)
        other = Event.objects.create(
            name="Other",
            dojo=self.event.dojo,
            places=5,
            start_time=self.event.start_time,
            end_time=self.event.end_time,
        )
        foreign = other.questions.create(text="Theirs?")
        bad = f"/api/v1/events/{self.event.id}/attendance/children/{self.registration.id}/answers/{foreign.id}"
        self.assertEqual(
            self.client.put(bad, {"answer": True}, content_type="application/json", **auth).status_code, 404
        )
        _client, read_only = self.bearer([DojoApiClient.READ])
        self.assertEqual(
            self.client.put(url, {"answer": False}, content_type="application/json", **read_only).status_code, 403
        )

    def test_another_dojos_event_is_a_404(self):
        _client, auth = self.bearer()
        other = make_dojo("Leuven", champion=make_champion(username="olga"))
        event = Event.objects.create(
            name="Elsewhere", dojo=other, places=5, start_time=self.event.start_time, end_time=self.event.end_time
        )
        self.assertEqual(self.client.get(f"/api/v1/events/{event.id}/attendance", **auth).status_code, 404)

    def test_marking_needs_the_write_scope(self):
        _client, auth = self.bearer([DojoApiClient.READ])
        url = f"/api/v1/events/{self.event.id}/attendance/children/{self.registration.id}"
        response = self.client.put(url, {"attended": True}, content_type="application/json", **auth)
        self.assertEqual(response.status_code, 403)
        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.attended)

    def test_mark_a_child_as_the_client(self):
        from auditlog.models import LogEntry

        client, auth = self.bearer()
        url = f"/api/v1/events/{self.event.id}/attendance/children/{self.registration.id}"
        response = self.client.put(url, {"attended": True}, content_type="application/json", **auth)
        self.assertEqual(response.json()["attended"], True)
        self.registration.refresh_from_db()
        self.assertTrue(self.registration.attended)
        entry = LogEntry.objects.get_for_object(self.registration).latest("timestamp")
        self.assertEqual(entry.actor, client.account)
        # Back to not marked.
        self.client.put(url, {"attended": None}, content_type="application/json", **auth)
        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.attended)

    def test_a_waitlisted_child_cant_be_marked(self):
        _client, auth = self.bearer()
        waiting = Registration.objects.get(waiting_list=True)
        url = f"/api/v1/events/{self.event.id}/attendance/children/{waiting.id}"
        response = self.client.put(url, {"attended": True}, content_type="application/json", **auth)
        self.assertEqual(response.status_code, 404)

    def test_mark_the_team_and_everyone(self):
        client, auth = self.bearer()
        url = f"/api/v1/events/{self.event.id}/attendance/team/{self.mentor_membership.id}"
        self.client.put(url, {"attended": False}, content_type="application/json", **auth)
        record = TeamAttendance.objects.get(event=self.event, membership=self.mentor_membership)
        self.assertEqual((record.attended, record.marked_by), (False, client.account))
        data = self.client.post(f"/api/v1/events/{self.event.id}/attendance/all-present", **auth).json()
        self.assertEqual([c["attended"] for c in data["children"]], [True])
        self.assertEqual([m["attended"] for m in data["team"]], [True])

    def test_a_deleted_clients_token_stops_working(self):
        client, auth = self.bearer()
        services.delete_client(client)
        self.assertEqual(self.client.get("/api/v1/events", **auth).status_code, 401)

    def test_the_spec_describes_oauth2_client_credentials_and_scopes(self):
        from django.conf import settings

        from .v1 import api

        spec = api.get_openapi_schema()
        scheme = spec["components"]["securitySchemes"]["OAuth2"]
        self.assertEqual(scheme["type"], "oauth2")
        flow = scheme["flows"]["clientCredentials"]
        self.assertEqual(flow["tokenUrl"], reverse("oauth2_token"))
        self.assertEqual(flow["scopes"], settings.OAUTH2_PROVIDER["SCOPES"])
        needs = {
            (method, path): operation["security"]
            for path, operations in spec["paths"].items()
            for method, operation in operations.items()
        }
        # Either scope will do: one entry each (OpenAPI reads the entries as "or").
        self.assertEqual(
            needs[("get", "/api/v1/events")],
            [{"OAuth2": [DojoApiClient.READ]}, {"OAuth2": [DojoApiClient.EVENTS_READ]}],
        )
        self.assertEqual(
            needs[("put", "/api/v1/events/{event_id}/attendance/children/{registration_id}")],
            [{"OAuth2": [DojoApiClient.WRITE]}],
        )
        self.assertEqual(needs[("post", "/api/v1/events/sync")], [{"OAuth2": [DojoApiClient.EVENTS_WRITE]}])
        for (method, path), security in needs.items():
            self.assertTrue(security, (method, path))
            for entry in security:
                self.assertEqual(len(entry["OAuth2"]), 1, (method, path))
            self.assertIn(401, spec["paths"][path][method]["responses"])

    def test_the_schema_never_holds_sensitive_fields(self):
        """No field classified special (health), criminal or security, and
        nothing kept out of a person's export, is part of the API."""
        from core import privacy_registry as registry
        from core.privacy_registry import Category

        from .v1 import api

        sensitive = {
            name
            for entry in registry.registered()
            for name, spec in entry.fields.items()
            if spec.category in (Category.SPECIAL, Category.CRIMINAL, Category.SECURITY) or not spec.export
        }
        properties = set()
        for schema in api.get_openapi_schema()["components"]["schemas"].values():
            properties |= set(schema.get("properties", {}))
        self.assertEqual(properties & sensitive, set())


class EventSyncApiTests(ApiTestCase):
    """POST /api/v1/events/sync: a dojo's planned sessions from a spreadsheet
    (DATA_MODEL_API.md §13, decision 6)."""

    URL = "/api/v1/events/sync"

    def setUp(self):
        super().setUp()
        self.day = (timezone.localdate() + timedelta(days=30)).isoformat()

    def row(self, ref="2026-W1", **fields):
        return {
            "external_ref": ref,
            "name": "Coding Saturday",
            "date": self.day,
            "start_time": "14:00",
            "end_time": "17:00",
            "places": 20,
            **fields,
        }

    def sync(self, auth, *rows):
        response = self.client.post(self.URL, {"events": list(rows)}, content_type="application/json", **auth)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def planner(self):
        return self.bearer([DojoApiClient.EVENTS_WRITE])

    def test_needs_the_events_write_scope(self):
        _client, auth = self.bearer([DojoApiClient.READ, DojoApiClient.WRITE, DojoApiClient.EVENTS_READ])
        response = self.client.post(self.URL, {"events": [self.row()]}, content_type="application/json", **auth)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Event.objects.filter(external_ref="2026-W1").exists())

    def test_a_new_key_adds_a_draft_session_with_the_dojos_pathways(self):
        from pathways.models import Pathway

        pathway = Pathway.objects.create(name="Scratch")
        self.dojo.pathways.add(pathway)
        client, auth = self.planner()
        [result] = self.sync(auth, self.row(venue_name="Library", min_age=7, max_age=12))
        event = Event.objects.get(external_ref="2026-W1")
        self.assertEqual(result, {"external_ref": "2026-W1", "outcome": "created", "event_id": event.id, "detail": ""})
        self.assertEqual(
            (event.dojo, event.status, event.name, event.places, event.venue_name, event.min_age, event.max_age),
            (self.dojo, Event.DRAFT, "Coding Saturday", 20, "Library", 7, 12),
        )
        self.assertEqual((event.start_time.hour, event.end_time.hour), (14, 17))
        self.assertEqual(list(event.pathways.all()), [pathway])

    def test_the_same_key_updates_the_same_session(self):
        _client, auth = self.planner()
        self.sync(auth, self.row())
        [result] = self.sync(auth, self.row(name="Robots", places=12, status="open"))
        event = Event.objects.get(external_ref="2026-W1")
        self.assertEqual(result["outcome"], "updated")
        self.assertEqual((event.name, event.places, event.status), ("Robots", 12, Event.OPEN))
        self.assertIsNotNone(event.published_at)
        self.assertEqual(Event.objects.filter(dojo=self.dojo).count(), 2)  # the setUp session and this one

    def test_running_it_again_changes_nothing(self):
        from auditlog.models import LogEntry

        client, auth = self.planner()
        self.sync(auth, self.row())
        event = Event.objects.get(external_ref="2026-W1")
        entries = LogEntry.objects.get_for_object(event).count()
        [result] = self.sync(auth, self.row())
        self.assertEqual(result["outcome"], "unchanged")
        self.assertEqual(LogEntry.objects.get_for_object(event).count(), entries)
        self.assertEqual(LogEntry.objects.get_for_object(event).latest("timestamp").actor, client.account)

    def test_a_blank_status_keeps_the_sessions_status(self):
        _client, auth = self.planner()
        self.sync(auth, self.row(status="open"))
        [result] = self.sync(auth, self.row(status="", places=25))
        self.assertEqual(result["outcome"], "updated")
        self.assertEqual(Event.objects.get(external_ref="2026-W1").status, Event.OPEN)

    def test_one_bad_row_never_stops_the_others(self):
        _client, auth = self.planner()
        results = self.sync(
            auth,
            self.row("a"),
            self.row("b", end_time="13:00"),
            self.row("c", places="many"),
            self.row("d", min_age=12, max_age=8),
            self.row("e", date=(timezone.localdate() - timedelta(days=1)).isoformat()),
            self.row("a", name="Twice"),
            self.row("f", status="published"),
            self.row("g"),
        )
        self.assertEqual(
            [(r["external_ref"], r["outcome"]) for r in results],
            [
                ("a", "created"),
                ("b", "error"),
                ("c", "error"),
                ("d", "error"),
                ("e", "error"),
                ("a", "error"),
                ("f", "error"),
                ("g", "created"),
            ],
        )
        self.assertIn("places", results[2]["detail"])
        self.assertTrue(all(r["detail"] for r in results if r["outcome"] == "error"))
        self.assertEqual(
            sorted(Event.objects.exclude(external_ref=None).values_list("external_ref", flat=True)), ["a", "g"]
        )
        self.assertEqual(Event.objects.get(external_ref="a").name, "Coding Saturday")

    def test_a_session_that_has_started_is_left_alone(self):
        _client, auth = self.planner()
        self.sync(auth, self.row())
        start = timezone.now() - timedelta(hours=1)
        Event.objects.filter(external_ref="2026-W1").update(start_time=start, end_time=start + timedelta(hours=3))
        [result] = self.sync(auth, self.row(name="Changed"))
        self.assertEqual(result["outcome"], "skipped")
        self.assertEqual(Event.objects.get(external_ref="2026-W1").name, "Coding Saturday")

    def test_never_deletes(self):
        _client, auth = self.planner()
        self.sync(auth, self.row("a"), self.row("b"))
        self.sync(auth, self.row("a"))
        self.assertTrue(Event.objects.filter(external_ref="b").exists())

    def test_keys_belong_to_one_dojo(self):
        other = make_dojo("Leuven", champion=make_champion(username="olga"))
        start = timezone.now() + timedelta(days=10)
        theirs = Event.objects.create(
            name="Theirs",
            dojo=other,
            places=5,
            start_time=start,
            end_time=start + timedelta(hours=2),
            external_ref="a",
        )
        _client, auth = self.planner()
        [result] = self.sync(auth, self.row("a"))
        self.assertEqual(result["outcome"], "created")
        theirs.refresh_from_db()
        self.assertEqual(theirs.name, "Theirs")
        self.assertEqual(Event.objects.filter(external_ref="a").count(), 2)

    def test_excel_values(self):
        """Numbers as Excel sends them: a decimal key and places, a serial date and a fraction-of-a-day time."""
        from datetime import date

        _client, auth = self.planner()
        day = timezone.localdate() + timedelta(days=30)
        serial = (day - date(1899, 12, 30)).days
        [result] = self.sync(
            auth, self.row(202601.0, date=float(serial), start_time=14 / 24, end_time=0.75, places=20.0)
        )
        self.assertEqual(result["external_ref"], "202601")
        event = Event.objects.get(external_ref="202601")
        self.assertEqual((event.start_time.date(), event.start_time.hour, event.end_time.hour), (day, 14, 18))
        self.assertEqual(self.sync(auth, self.row("x", date=day.strftime("%d/%m/%Y")))[0]["outcome"], "created")

    def test_at_most_200_rows(self):
        _client, auth = self.planner()
        rows = [self.row(str(n)) for n in range(201)]
        response = self.client.post(self.URL, {"events": rows}, content_type="application/json", **auth)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Event.objects.exclude(external_ref=None).exists())

    def test_listing_sessions_takes_either_read_scope(self):
        _client, auth = self.bearer([DojoApiClient.EVENTS_READ])
        Event.objects.filter(pk=self.event.pk).update(external_ref="w1")
        [event] = self.client.get("/api/v1/events", **auth).json()
        self.assertEqual(event["external_ref"], "w1")
        # But not the attendance.
        self.assertEqual(self.client.get(f"/api/v1/events/{self.event.id}/attendance", **auth).status_code, 403)


class CorsTests(ApiTestCase):
    """Tools that run in a browser (Excel on the web, a dojo's own page) may
    call the API from another site (settings.CORS_*); never with the site's
    cookies, and the rest of the site allows no other site."""

    ORIGIN = "https://dojo.example.org"

    def preflight(self, path, headers="authorization, content-type"):
        return self.client.options(
            path,
            HTTP_ORIGIN=self.ORIGIN,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS=headers,
        )

    def test_the_api_and_the_token_endpoint_allow_any_site(self):
        for path in ("/api/v1/events/sync", reverse("oauth2_token")):
            response = self.preflight(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(response["Access-Control-Allow-Origin"], "*", path)
            self.assertIn("authorization", response["Access-Control-Allow-Headers"], path)
            self.assertNotIn("Access-Control-Allow-Credentials", response, path)

    def test_a_call_from_another_site_gets_its_answer(self):
        _client, auth = self.bearer()
        response = self.client.get("/api/v1/events", HTTP_ORIGIN=self.ORIGIN, **auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")

    def test_the_rest_of_the_site_allows_no_other_site(self):
        for path in ("/", reverse("login"), reverse("dojo_api_clients", args=[self.dojo.id])):
            response = self.client.get(path, HTTP_ORIGIN=self.ORIGIN)
            self.assertNotIn("Access-Control-Allow-Origin", response, path)


class ServiceAccountTests(ApiTestCase):
    def test_left_out_of_retention_and_deletion(self):
        from privacy.deletion import preview
        from privacy.retention import candidates

        client, _id, _secret = self.make_client()
        User.objects.filter(pk=client.account.pk).update(date_joined=timezone.now() - timedelta(days=2000))
        self.assertNotIn(client.account, candidates())
        self.assertFalse(preview(client.account).possible)

    def test_cant_log_in(self):
        client, _id, _secret = self.make_client()
        self.assertFalse(self.client.login(username=client.account.username, password=""))
        self.assertEqual(DojoMembership.objects.filter(user=client.account).count(), 0)
