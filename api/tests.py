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
        self.assertTrue(response.context["error"])
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
            data["children"], [{"registration_id": self.registration.id, "name": "Lotte", "attended": None}]
        )
        self.assertEqual([m["membership_id"] for m in data["team"]], [self.mentor_membership.id])
        self.assertNotIn("Peanuts", str(data))

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
        self.assertEqual(needs[("get", "/api/v1/events")], [{"OAuth2": [DojoApiClient.READ]}])
        self.assertEqual(
            needs[("put", "/api/v1/events/{event_id}/attendance/children/{registration_id}")],
            [{"OAuth2": [DojoApiClient.WRITE]}],
        )
        for (method, path), security in needs.items():
            self.assertEqual(len(security), 1, (method, path))
            self.assertEqual(len(security[0]["OAuth2"]), 1, (method, path))
            self.assertIn(401, spec["paths"][path][method]["responses"])

    def test_the_schema_never_holds_sensitive_fields(self):
        """No field classified special (health), criminal or security, and
        nothing kept out of a person's export, is part of the API."""
        from privacy import registry
        from privacy.registry import Category

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
