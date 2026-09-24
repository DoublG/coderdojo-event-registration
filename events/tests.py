from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guardianship, Participant, User
from dojos.models import Dojo

from .models import Event, Registration


def _future_event(dojo, **kwargs):
    now = timezone.now()
    defaults = {
        "name": "Session",
        "dojo": dojo,
        "status": Event.OPEN,
        "start_time": now + timedelta(days=7),
        "end_time": now + timedelta(days=7, hours=2),
        "places": 10,
    }
    defaults.update(kwargs)
    return Event.objects.create(**defaults)


class EventListViewTests(TestCase):
    def test_renders_upcoming_events(self):
        dojo = Dojo.objects.create(name="Ghent")
        _future_event(dojo)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/event_list.html")
        self.assertEqual(len(response.context["events"]), 1)

    def test_htmx_request_returns_partial_template(self):
        response = self.client.get(reverse("event_list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/partials/_event_results_page.html")

    def test_filters_by_dojo(self):
        ghent = Dojo.objects.create(name="Ghent")
        antwerp = Dojo.objects.create(name="Antwerp")
        ghent_event = _future_event(ghent)
        _future_event(antwerp)

        response = self.client.get(reverse("event_list"), {"dojo": ghent.id})

        self.assertEqual(list(response.context["events"]), [ghent_event])

    def test_draft_event_is_hidden(self):
        dojo = Dojo.objects.create(name="Ghent")
        _future_event(dojo, status=Event.DRAFT)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(len(response.context["events"]), 0)

    def test_closed_event_still_shown(self):
        dojo = Dojo.objects.create(name="Ghent")
        event = _future_event(dojo, status=Event.CLOSED)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(list(response.context["events"]), [event])


class UpcomingSessionsWidgetViewTests(TestCase):
    def test_renders_partial(self):
        cache.clear()  # upcoming_available_events() is cached (events/search.py)
        dojo = Dojo.objects.create(name="Ghent")
        _future_event(dojo)
        response = self.client.get(reverse("upcoming_sessions_widget"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/partials/_upcoming_sessions_page.html")


class EventDetailViewTests(TestCase):
    def test_existing_event_renders(self):
        dojo = Dojo.objects.create(name="Ghent")
        event = _future_event(dojo)
        response = self.client.get(reverse("event_detail", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["event"], event)

    def test_missing_event_is_404(self):
        response = self.client.get(reverse("event_detail", kwargs={"event_id": 999999}))
        self.assertEqual(response.status_code, 404)

    def test_draft_event_is_404(self):
        dojo = Dojo.objects.create(name="Ghent")
        event = _future_event(dojo, status=Event.DRAFT)
        response = self.client.get(reverse("event_detail", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 404)


class EventSignupViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dojo = Dojo.objects.create(name="Ghent")
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.child = Participant.objects.create(name="Kid One")
        Guardianship.objects.create(guardian=cls.guardian, ninja=cls.child)

    def test_login_required(self):
        event = _future_event(self.dojo)
        response = self.client.get(reverse("event_signup", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_signup_confirms_when_places_available(self):
        event = _future_event(self.dojo, places=10)
        self.client.force_login(self.guardian)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertEqual(response.status_code, 200)
        registration = Registration.objects.get(event=event, participant=self.child)
        self.assertFalse(registration.waiting_list)
        self.assertEqual(response.context["results"][0]["waiting_list"], False)

    def test_cannot_sign_up_another_familys_ninja(self):
        """Only ninjas the account is a guardian of can be signed up — a
        foreign child id in the POST is silently ignored."""
        other_parent = User.objects.create(username="g2", email="g2@example.com")
        event = _future_event(self.dojo, places=10)
        self.client.force_login(other_parent)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertEqual(response.context["error"], "Please select at least one child.")
        self.assertFalse(Registration.objects.filter(event=event).exists())

    def test_ninja_login_cannot_sign_anyone_up(self):
        ninja_login = User.objects.create(username="kid", account_type=User.NINJA)
        self.child.account = ninja_login
        self.child.save(update_fields=["account"])
        event = _future_event(self.dojo, places=10)
        self.client.force_login(ninja_login)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertEqual(response.context["children"], [])
        self.assertFalse(Registration.objects.filter(event=event).exists())

    def test_signup_waitlists_when_full(self):
        event = _future_event(self.dojo, places=0)
        self.client.force_login(self.guardian)

        self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        registration = Registration.objects.get(event=event, participant=self.child)
        self.assertTrue(registration.waiting_list)

    def test_signup_with_no_children_selected_shows_error(self):
        event = _future_event(self.dojo)
        self.client.force_login(self.guardian)

        response = self.client.post(reverse("event_signup", kwargs={"event_id": event.id}), {})

        self.assertIsNotNone(response.context["error"])
        self.assertEqual(Registration.objects.count(), 0)

    def test_already_registered_child_cannot_double_signup(self):
        event = _future_event(self.dojo)
        Registration.objects.create(event=event, participant=self.child, waiting_list=False, position=1)
        self.client.force_login(self.guardian)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertIsNotNone(response.context["error"])
        self.assertEqual(Registration.objects.filter(event=event, participant=self.child).count(), 1)

    def test_closed_event_blocks_signup(self):
        event = _future_event(self.dojo, status=Event.CLOSED)
        self.client.force_login(self.guardian)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertIsNotNone(response.context["error"])
        self.assertEqual(Registration.objects.count(), 0)

    def test_draft_event_signup_is_404(self):
        event = _future_event(self.dojo, status=Event.DRAFT)
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("event_signup", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 404)
