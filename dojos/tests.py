from datetime import date, datetime, time
from unittest.mock import patch

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import DojoOwner, Guardian, HelperAccount, Participant
from accounts.provisioning import attach_role
from events.models import Event, Registration
from geo.models import AdministrativeBoundary
from notifications.consumers import NotificationConsumer
from notifications.services import notify

from . import access
from .models import Dojo, Mentor

IN_MEMORY_CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


class DojoListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Dojo.objects.create(name="Ghent", location=Point(3.7174, 51.0543, srid=4326))
        Dojo.objects.create(name="Antwerp", location=Point(4.4025, 51.2194, srid=4326))

    def setUp(self):
        # The default-origin search result is cached (dojos/search.py) — the
        # test DB resets between tests/classes, the cache doesn't.
        cache.clear()

    def test_default_search_orders_by_distance_from_ghent(self):
        """No search submitted yet — falls back to the default (Ghent)
        origin, so results are still ordered nearest-first."""
        response = self.client.get(reverse("dojo_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/dojo_list.html")
        names = [dojo.name for dojo in response.context["dojos"]]
        self.assertEqual(names, ["Ghent", "Antwerp"])

    def test_htmx_request_returns_partial_template(self):
        response = self.client.get(reverse("dojo_list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/partials/_dojo_results_page.html")

    @patch("dojos.search.geocode")
    def test_typed_location_uses_geocoded_origin(self, mock_geocode):
        mock_geocode.return_value = (51.2194, 4.4025)  # Antwerp
        response = self.client.get(reverse("dojo_list"), {"location": "Antwerp"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["geocode_failed"])
        names = [dojo.name for dojo in response.context["dojos"]]
        self.assertEqual(names[0], "Antwerp")

    @patch("dojos.search.geocode")
    def test_failed_geocode_sets_flag_and_unordered_results(self, mock_geocode):
        mock_geocode.return_value = None
        response = self.client.get(reverse("dojo_list"), {"location": "Nowhereville"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["geocode_failed"])


class DojoFinderWidgetViewTests(TestCase):
    def test_renders_partial(self):
        cache.clear()  # see DojoListViewTests.setUp — same default-origin cache key
        Dojo.objects.create(name="Ghent", location=Point(3.7174, 51.0543, srid=4326))
        response = self.client.get(reverse("dojo_finder_widget"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/partials/_dojo_finder_widget_results.html")


class DojoDetailViewTests(TestCase):
    def test_existing_dojo_renders(self):
        dojo = Dojo.objects.create(name="Ghent")
        response = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": dojo.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dojo"], dojo)

    def test_missing_dojo_is_404(self):
        response = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": 999999}))
        self.assertEqual(response.status_code, 404)


class DojoTeamViewTests(TestCase):
    def test_renders_with_lead_coach_first(self):
        dojo = Dojo.objects.create(name="Ghent")
        owner = DojoOwner.objects.create(username="owner1")
        dojo.owner = owner
        dojo.save()
        # "Aaron" sorts before the owner's username — Lead Coach still comes first.
        Mentor.objects.create(name="Aaron Volunteer", dojo=dojo, role=Mentor.VOLUNTEER)

        response = self.client.get(reverse("dojo_team", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.status_code, 200)
        mentors = list(response.context["mentors"])
        self.assertEqual(mentors[0].role, Mentor.LEAD_COACH)
        self.assertEqual(mentors[0].owner_account_id, owner.pk)


class LeadCoachSyncTests(TestCase):
    """A dojo's owner *is* its Lead Coach — Dojo.sync_lead_coach keeps one
    LEAD_COACH Mentor per dojo, linked to the current owner."""

    def test_setting_an_owner_creates_their_lead_coach_profile(self):
        owner = DojoOwner.objects.create(username="owner1", first_name="Ada", last_name="Lovelace", email="ada@example.com")

        dojo = Dojo.objects.create(name="Ghent", owner=owner)

        lead = dojo.mentors.get(role=Mentor.LEAD_COACH)
        self.assertEqual(lead.owner_account_id, owner.pk)
        self.assertEqual(lead.name, "Ada Lovelace")
        self.assertEqual(lead.email, "ada@example.com")

    def test_owner_of_several_dojos_is_lead_coach_of_each(self):
        owner = DojoOwner.objects.create(username="owner1")
        ghent = Dojo.objects.create(name="Ghent", owner=owner)
        antwerp = Dojo.objects.create(name="Antwerp", owner=owner)

        self.assertEqual(
            set(Mentor.objects.filter(owner_account=owner, role=Mentor.LEAD_COACH).values_list("dojo", flat=True)),
            {ghent.id, antwerp.id},
        )

    def test_saving_again_creates_no_duplicate(self):
        dojo = Dojo.objects.create(name="Ghent", owner=DojoOwner.objects.create(username="owner1"))
        dojo.save()
        dojo.save()
        self.assertEqual(dojo.mentors.filter(role=Mentor.LEAD_COACH).count(), 1)

    def test_changing_owner_demotes_previous_lead_coach_and_keeps_history(self):
        old_owner = DojoOwner.objects.create(username="old")
        new_owner = DojoOwner.objects.create(username="new")
        dojo = Dojo.objects.create(name="Ghent", owner=old_owner)
        old_lead = dojo.mentors.get(role=Mentor.LEAD_COACH)
        event = Event.objects.create(
            name="Past", dojo=dojo, start_time="2020-01-01T10:00:00Z", end_time="2020-01-01T12:00:00Z", places=10
        )
        event.mentors.add(old_lead)

        dojo.owner = new_owner
        dojo.save()

        old_lead.refresh_from_db()
        self.assertEqual(old_lead.role, Mentor.VOLUNTEER)
        self.assertIsNone(old_lead.owner_account_id)
        self.assertEqual(list(event.mentors.all()), [old_lead])
        new_lead = dojo.mentors.get(role=Mentor.LEAD_COACH)
        self.assertEqual(new_lead.owner_account_id, new_owner.pk)

    def test_removing_owner_leaves_no_lead_coach(self):
        dojo = Dojo.objects.create(name="Ghent", owner=DojoOwner.objects.create(username="owner1"))
        dojo.owner = None
        dojo.save()
        self.assertFalse(dojo.mentors.filter(role=Mentor.LEAD_COACH).exists())

    def test_second_lead_coach_fails_validation(self):
        owner = DojoOwner.objects.create(username="owner1")
        dojo = Dojo.objects.create(name="Ghent", owner=owner)
        other = DojoOwner.objects.create(username="owner2")
        extra = Mentor(name="Extra", dojo=dojo, role=Mentor.LEAD_COACH, owner_account=other)
        with self.assertRaises(ValidationError):
            extra.clean()


class DojoDashboardViewTests(TestCase):
    def test_dojo_with_no_sessions_still_renders(self):
        owner = DojoOwner.objects.create(username="owner1")
        dojo = Dojo.objects.create(name="Ghent", owner=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["session"])

    def test_shows_real_registrations_for_next_session(self):
        owner = DojoOwner.objects.create(username="owner1")
        dojo = Dojo.objects.create(name="Ghent", owner=owner)
        event = Event.objects.create(
            name="Session", dojo=dojo, status=Event.OPEN,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10
        )
        registration = Registration.objects.create(
            event=event, participant=Participant.objects.create(name="Mila"), waiting_list=False,
            position=1, attended=True,
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.context["session"], event)
        self.assertEqual(response.context["registrations"], [registration])
        self.assertContains(response, "Mila")
        self.assertContains(response, "1 of 1 present")

    def test_missing_dojo_is_404(self):
        owner = DojoOwner.objects.create(username="owner1")
        self.client.force_login(owner)
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": 999999}))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_redirected_to_login(self):
        dojo = Dojo.objects.create(name="Ghent")
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        owner = DojoOwner.objects.create(username="owner1")
        other_owner = DojoOwner.objects.create(username="owner2")
        dojo = Dojo.objects.create(name="Ghent", owner=owner)
        self.client.force_login(other_owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.status_code, 404)


class DojoManageViewTests(TestCase):
    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner, address="Oude Vismijn 3, Ghent")

    def _valid_post_data(self, **overrides):
        data = {
            "name": "CoderDojo Ghent",
            "tagline": "Build something awesome.",
            "description": "A friendly Saturday coding club.",
            "schedule_description": "Every 2nd Saturday",
            "min_age": "7",
            "max_age": "18",
            "email": "ghent@example.org",
            "phone": "+32 470 00 00 00",
            "municipality": "",
            "address": "Oude Vismijn 3, Ghent",
            "visit_notes": "Ring the bell at the side entrance.",
        }
        data.update(overrides)
        return data

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        other_owner = DojoOwner.objects.create(username="owner2")
        self.client.force_login(other_owner)
        response = self.client.get(reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 404)

    def test_get_renders_form_prefilled_from_dojo(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].instance, self.dojo)

    def test_valid_post_updates_dojo_without_address_change(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(tagline="Updated tagline"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["saved"])
        self.dojo.refresh_from_db()
        self.assertEqual(self.dojo.tagline, "Updated tagline")

    @patch("dojos.views.geocode")
    def test_address_change_geocodes_and_updates_province(self, mock_geocode):
        mock_geocode.return_value = (51.2194, 4.4025)  # Antwerp
        province = AdministrativeBoundary.objects.create(
            kind=AdministrativeBoundary.PROVINCE, name="Antwerp",
            boundary=MultiPolygon(Polygon(((4, 51), (4, 52), (5, 52), (5, 51), (4, 51)))),
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(address="Some new address, Antwerp"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["geocode_failed"])
        self.dojo.refresh_from_db()
        self.assertAlmostEqual(self.dojo.location.y, 51.2194)
        self.assertAlmostEqual(self.dojo.location.x, 4.4025)
        self.assertEqual(self.dojo.province, province)

    @patch("dojos.views.geocode")
    def test_failed_geocode_still_saves_other_fields(self, mock_geocode):
        mock_geocode.return_value = None
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(address="Nowhereville", tagline="Still saved"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["saved"])
        self.assertTrue(response.context["geocode_failed"])
        self.dojo.refresh_from_db()
        self.assertEqual(self.dojo.tagline, "Still saved")

    def test_unchanged_address_does_not_geocode(self):
        self.client.force_login(self.owner)
        with patch("dojos.views.geocode") as mock_geocode:
            self.client.post(
                reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}),
                self._valid_post_data(),  # address unchanged from setUp
            )
        mock_geocode.assert_not_called()

    def test_template_icon_used_when_no_file_uploaded(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(template_icon="icon-02-robot.svg"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["saved"])
        self.dojo.refresh_from_db()
        self.assertTrue(self.dojo.icon)
        self.assertIn("icon-02-robot", self.dojo.icon.name)


class DojoEventListViewTests(TestCase):
    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        other_owner = DojoOwner.objects.create(username="owner2")
        self.client.force_login(other_owner)
        response = self.client.get(reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 404)

    def test_lists_events_including_drafts(self):
        """Unlike the public event list, the owner's own list must show
        every status — draft included — since this is where they'd publish
        one from."""
        draft = Event.objects.create(
            name="Draft session", dojo=self.dojo, status=Event.DRAFT,
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/dojo_event_list.html")
        self.assertEqual(list(response.context["events"]), [draft])


class DojoEventCreateViewTests(TestCase):
    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)

    def _valid_post_data(self, **overrides):
        data = {
            "name": "Coding Saturday",
            "event_date": "01/01/2030",
            "start_time": "10:00",
            "end_time": "12:00",
            "places": "20",
            "venue_name": "",
            "template_image": "",
            "description": "",
            "min_age": "",
            "max_age": "",
            "mentors": [],
        }
        data.update(overrides)
        return data

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        other_owner = DojoOwner.objects.create(username="owner2")
        self.client.force_login(other_owner)
        response = self.client.get(reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 404)

    def test_valid_post_creates_draft_event_and_redirects_to_list(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}), self._valid_post_data()
        )

        self.assertRedirects(response, reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))
        event = Event.objects.get(dojo=self.dojo)
        self.assertEqual(event.name, "Coding Saturday")
        self.assertEqual(event.status, Event.DRAFT)
        self.assertEqual(event.start_time.strftime("%d/%m/%Y %H:%M"), "01/01/2030 10:00")
        self.assertEqual(event.end_time.strftime("%d/%m/%Y %H:%M"), "01/01/2030 12:00")

    def test_invalid_post_reshows_form_without_creating(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(end_time="09:00"),  # before start_time, same day
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Event.objects.count(), 0)

    def test_mentor_choices_scoped_to_dojo(self):
        other_dojo = Dojo.objects.create(name="Antwerp")
        Mentor.objects.create(name="Elsewhere", dojo=other_dojo, role=Mentor.VOLUNTEER)
        own_mentor = Mentor.objects.create(name="Own Mentor", dojo=self.dojo, role=Mentor.VOLUNTEER)
        self.client.force_login(self.owner)

        response = self.client.get(reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}))

        # The owner's own Lead Coach profile is a choice too — they can run a session themselves.
        lead_coach = self.dojo.mentors.get(role=Mentor.LEAD_COACH)
        self.assertEqual(set(response.context["form"].fields["mentors"].queryset), {own_mentor, lead_coach})

    def test_multiple_mentors_can_be_assigned(self):
        mentor_a = Mentor.objects.create(name="Mentor A", dojo=self.dojo, role=Mentor.VOLUNTEER)
        mentor_b = Mentor.objects.create(name="Mentor B", dojo=self.dojo, role=Mentor.VOLUNTEER)
        self.client.force_login(self.owner)

        self.client.post(
            reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(mentors=[str(mentor_a.id), str(mentor_b.id)]),
        )

        event = Event.objects.get(dojo=self.dojo)
        self.assertEqual(set(event.mentors.all()), {mentor_a, mentor_b})

    def test_template_image_used_when_no_file_uploaded(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(template_image="coding-saturday.svg"),
        )

        self.assertRedirects(response, reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))
        event = Event.objects.get(dojo=self.dojo)
        self.assertTrue(event.image)
        self.assertIn("coding-saturday", event.image.name)


class DojoEventDetailViewTests(TestCase):
    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)
        self.event = Event.objects.create(
            name="Session", dojo=self.dojo, status=Event.OPEN,
            start_time=timezone.make_aware(datetime(2030, 1, 1, 10, 0)),
            end_time=timezone.make_aware(datetime(2030, 1, 1, 12, 0)),
            places=10,
        )

    def _url(self, event=None):
        return reverse("dojo_event_detail", kwargs={"dojo_id": self.dojo.id, "event_id": (event or self.event).id})

    def _valid_post_data(self, **overrides):
        data = {
            "name": "Renamed session",
            "event_date": "02/02/2030",
            "start_time": "14:00",
            "end_time": "16:30",
            "places": "25",
            "venue_name": "Library",
            "template_image": "",
            "description": "",
            "min_age": "",
            "max_age": "",
            "mentors": [],
        }
        data.update(overrides)
        return data

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        other_owner = DojoOwner.objects.create(username="owner2")
        self.client.force_login(other_owner)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 404)

    def test_event_of_another_dojo_gets_404(self):
        """Owning *a* dojo isn't enough — the event must belong to the dojo
        in the URL, or an owner could edit any event by swapping ids."""
        other_dojo = Dojo.objects.create(name="Antwerp")
        other_event = Event.objects.create(
            name="Elsewhere", dojo=other_dojo,
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        self.client.force_login(self.owner)
        response = self.client.get(self._url(other_event))
        self.assertEqual(response.status_code, 404)

    def test_get_prefills_form_from_event(self):
        self.client.force_login(self.owner)

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/dojo_event_detail.html")
        form = response.context["form"]
        self.assertEqual(form.instance, self.event)
        self.assertEqual(form["event_date"].value(), date(2030, 1, 1))
        self.assertEqual(form["start_time"].value(), time(10, 0))
        self.assertEqual(form["end_time"].value(), time(12, 0))

    def test_valid_post_saves_changes_in_place(self):
        self.client.force_login(self.owner)

        response = self.client.post(self._url(), self._valid_post_data())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["saved"])
        self.event.refresh_from_db()
        self.assertEqual(self.event.name, "Renamed session")
        self.assertEqual(self.event.places, 25)
        self.assertEqual(self.event.venue_name, "Library")
        self.assertEqual(timezone.localtime(self.event.start_time).strftime("%d/%m/%Y %H:%M"), "02/02/2030 14:00")
        self.assertEqual(timezone.localtime(self.event.end_time).strftime("%d/%m/%Y %H:%M"), "02/02/2030 16:30")
        # Saving the form never touches status — that's dojo_event_set_status' job.
        self.assertEqual(self.event.status, Event.OPEN)

    def test_invalid_post_reshows_form_without_saving(self):
        self.client.force_login(self.owner)

        response = self.client.post(self._url(), self._valid_post_data(end_time="13:00"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["saved"])
        self.assertTrue(response.context["form"].errors)
        self.event.refresh_from_db()
        self.assertEqual(self.event.name, "Session")

    def test_event_list_links_to_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))
        self.assertContains(response, self._url())


class DojoEventAttendanceViewTests(TestCase):
    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)
        self.event = Event.objects.create(
            name="Session", dojo=self.dojo, status=Event.OPEN,
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        self.zoe = Registration.objects.create(
            event=self.event, participant=Participant.objects.create(name="Zoe"), waiting_list=False, position=1
        )
        self.anna = Registration.objects.create(
            event=self.event, participant=Participant.objects.create(name="Anna"), waiting_list=False, position=2
        )
        self.waitlisted = Registration.objects.create(
            event=self.event, participant=Participant.objects.create(name="Waitlisted"), waiting_list=True, position=3
        )

    def _page_url(self, event=None):
        return reverse("dojo_event_attendance", kwargs={"dojo_id": self.dojo.id, "event_id": (event or self.event).id})

    def _mark_url(self, registration):
        return reverse("dojo_event_attendance_mark", kwargs={
            "dojo_id": self.dojo.id, "event_id": self.event.id, "registration_id": registration.id,
        })

    def _mark_all_url(self):
        return reverse("dojo_event_attendance_mark_all", kwargs={"dojo_id": self.dojo.id, "event_id": self.event.id})

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self._page_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404_everywhere(self):
        other_owner = DojoOwner.objects.create(username="owner2")
        self.client.force_login(other_owner)
        self.assertEqual(self.client.get(self._page_url()).status_code, 404)
        self.assertEqual(self.client.post(self._mark_url(self.zoe), {"attended": "present"}).status_code, 404)
        self.assertEqual(self.client.post(self._mark_all_url()).status_code, 404)
        self.zoe.refresh_from_db()
        self.assertIsNone(self.zoe.attended)

    def test_event_of_another_dojo_gets_404(self):
        other_event = Event.objects.create(
            name="Elsewhere", dojo=Dojo.objects.create(name="Antwerp"),
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self._page_url(other_event)).status_code, 404)

    def test_registration_of_another_event_gets_404(self):
        """The registration id must belong to the event in the URL, or an
        owner could mark attendance on another dojo's session."""
        other_event = Event.objects.create(
            name="Elsewhere", dojo=Dojo.objects.create(name="Antwerp"),
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        other_registration = Registration.objects.create(
            event=other_event, participant=Participant.objects.create(name="Other"), waiting_list=False, position=1
        )
        self.client.force_login(self.owner)

        response = self.client.post(self._mark_url(other_registration), {"attended": "present"})

        self.assertEqual(response.status_code, 404)
        other_registration.refresh_from_db()
        self.assertIsNone(other_registration.attended)

    def test_page_lists_confirmed_registrations_alphabetically(self):
        self.client.force_login(self.owner)

        response = self.client.get(self._page_url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/dojo_event_attendance.html")
        self.assertEqual(response.context["registrations"], [self.anna, self.zoe])
        self.assertNotContains(response, "Waitlisted")

    def test_event_detail_links_to_attendance(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("dojo_event_detail", kwargs={"dojo_id": self.dojo.id, "event_id": self.event.id})
        )
        self.assertContains(response, self._page_url())

    def test_mark_present_absent_and_clear(self):
        self.client.force_login(self.owner)
        for value, expected in [("present", True), ("absent", False), ("none", None)]:
            with self.subTest(value=value):
                response = self.client.post(self._mark_url(self.zoe), {"attended": value})
                self.assertRedirects(response, self._page_url())
                self.zoe.refresh_from_db()
                self.assertEqual(self.zoe.attended, expected)

    def test_unknown_value_is_ignored(self):
        self.client.force_login(self.owner)
        self.client.post(self._mark_url(self.zoe), {"attended": "maybe"})
        self.zoe.refresh_from_db()
        self.assertIsNone(self.zoe.attended)

    def test_get_does_not_mark(self):
        self.client.force_login(self.owner)
        self.client.get(self._mark_url(self.zoe), {"attended": "present"})
        self.zoe.refresh_from_db()
        self.assertIsNone(self.zoe.attended)

    def test_waitlisted_registration_cannot_be_marked(self):
        self.client.force_login(self.owner)
        response = self.client.post(self._mark_url(self.waitlisted), {"attended": "present"})
        self.assertEqual(response.status_code, 404)

    def test_htmx_mark_returns_row_and_oob_summary(self):
        self.client.force_login(self.owner)

        response = self.client.post(self._mark_url(self.zoe), {"attended": "present"}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/partials/_attendance_row.html")
        content = response.content.decode()
        self.assertIn(f'id="attendance-row-{self.zoe.id}"', content)
        self.assertIn('hx-swap-oob="true"', content)
        self.assertIn("1 of 2 present", content)

    def test_mark_all_marks_only_confirmed_registrations(self):
        self.anna.attended = False
        self.anna.save(update_fields=["attended"])
        self.client.force_login(self.owner)

        response = self.client.post(self._mark_all_url())

        self.assertRedirects(response, self._page_url())
        self.zoe.refresh_from_db()
        self.anna.refresh_from_db()
        self.waitlisted.refresh_from_db()
        self.assertTrue(self.zoe.attended)
        self.assertTrue(self.anna.attended)
        self.assertIsNone(self.waitlisted.attended)

    def test_htmx_mark_all_returns_attendance_block(self):
        self.client.force_login(self.owner)

        response = self.client.post(self._mark_all_url(), HTTP_HX_REQUEST="true")

        self.assertTemplateUsed(response, "dojos/partials/_attendance.html")
        self.assertContains(response, "2 of 2 present")


class DojoEventSetStatusViewTests(TestCase):
    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)
        self.event = Event.objects.create(
            name="Session", dojo=self.dojo, status=Event.DRAFT,
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )

    def _url(self, event=None):
        return reverse("dojo_event_set_status", kwargs={"dojo_id": self.dojo.id, "event_id": (event or self.event).id})

    def _set_status(self, status):
        self.event.status = status
        self.event.save(update_fields=["status"])

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(self._url(), {"status": Event.OPEN})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.DRAFT)

    def test_another_owner_gets_404(self):
        other_owner = DojoOwner.objects.create(username="owner2")
        self.client.force_login(other_owner)
        response = self.client.post(self._url(), {"status": Event.OPEN})
        self.assertEqual(response.status_code, 404)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.DRAFT)

    def test_publish_moves_draft_to_open(self):
        self.client.force_login(self.owner)
        response = self.client.post(self._url(), {"status": Event.OPEN})
        self.assertRedirects(response, reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.OPEN)

    def test_every_status_reachable_from_every_other(self):
        """Not a one-way lifecycle — the owner can set any status from any
        other, including reopening a closed event and pulling one back to
        draft."""
        self.client.force_login(self.owner)
        statuses = [Event.DRAFT, Event.OPEN, Event.CLOSED]
        for from_status in statuses:
            for to_status in statuses:
                with self.subTest(from_status=from_status, to_status=to_status):
                    self._set_status(from_status)
                    self.client.post(self._url(), {"status": to_status})
                    self.event.refresh_from_db()
                    self.assertEqual(self.event.status, to_status)

    def test_closed_event_can_be_reopened(self):
        self._set_status(Event.CLOSED)
        self.client.force_login(self.owner)

        self.client.post(self._url(), {"status": Event.OPEN})

        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.OPEN)
        self.assertTrue(self.event.registration_open)

    def test_back_to_draft_keeps_registrations(self):
        self._set_status(Event.OPEN)
        participant = Participant.objects.create(name="Kid")
        Registration.objects.create(event=self.event, participant=participant, waiting_list=False, position=1)
        self.client.force_login(self.owner)

        self.client.post(self._url(), {"status": Event.DRAFT})

        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.DRAFT)
        self.assertEqual(self.event.registration_set.count(), 1)

    def test_unknown_status_is_ignored(self):
        self.client.force_login(self.owner)
        self.client.post(self._url(), {"status": "archived"})
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.DRAFT)

    def test_get_does_not_change_status(self):
        self.client.force_login(self.owner)
        self.client.get(self._url(), {"status": Event.OPEN})
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.DRAFT)

    def test_redirects_to_safe_next_url(self):
        self.client.force_login(self.owner)
        detail_url = reverse("dojo_event_detail", kwargs={"dojo_id": self.dojo.id, "event_id": self.event.id})

        response = self.client.post(self._url(), {"status": Event.OPEN, "next": detail_url})

        self.assertRedirects(response, detail_url)

    def test_ignores_offsite_next_url(self):
        self.client.force_login(self.owner)

        response = self.client.post(self._url(), {"status": Event.OPEN, "next": "https://evil.example/"})

        self.assertRedirects(response, reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))


class AdminNavDojoSwitcherTests(TestCase):
    """The dropdown in the admin sidebar's brand area
    (dojos/templates/dojos/_admin_base.html) that lets an owner of more
    than one dojo switch between them — only rendered at all once there's
    something to switch to."""

    def test_single_dojo_owner_sees_no_switcher(self):
        owner = DojoOwner.objects.create(username="owner1")
        dojo = Dojo.objects.create(name="Ghent", owner=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertNotContains(response, "data-cd-adminnav-switcher")
        self.assertContains(response, "Ghent")

    def test_multi_dojo_owner_sees_switcher_listing_every_dojo(self):
        owner = DojoOwner.objects.create(username="owner1")
        ghent = Dojo.objects.create(name="Ghent", owner=owner)
        antwerp = Dojo.objects.create(name="Antwerp", owner=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": ghent.id}))

        self.assertContains(response, "data-cd-adminnav-switcher")
        self.assertContains(response, "Ghent")
        self.assertContains(response, "Antwerp")
        # The switch-target link for the *other* dojo stays on the same
        # screen (Attendance here) rather than always landing on one page.
        self.assertContains(response, reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))

    def test_switch_links_go_to_manage_when_on_settings(self):
        owner = DojoOwner.objects.create(username="owner1")
        ghent = Dojo.objects.create(name="Ghent", owner=owner)
        antwerp = Dojo.objects.create(name="Antwerp", owner=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_manage", kwargs={"dojo_id": ghent.id}))

        self.assertContains(response, reverse("dojo_manage", kwargs={"dojo_id": antwerp.id}))

    def test_dojos_owned_by_someone_else_are_not_listed(self):
        owner = DojoOwner.objects.create(username="owner1")
        other_owner = DojoOwner.objects.create(username="owner2")
        dojo = Dojo.objects.create(name="Ghent", owner=owner)
        Dojo.objects.create(name="Antwerp", owner=other_owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertNotContains(response, "data-cd-adminnav-switcher")
        self.assertNotContains(response, "Antwerp")


class HelperDojoAccessTests(TestCase):
    """A HelperAccount linked to a dojo through its Mentor profile gets the
    dojo's admin area (dojos.access) — currently with every capability an
    owner has, but each one can be taken away via ROLE_CAPABILITIES."""

    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)
        self.helper = HelperAccount.objects.create(username="helper1", first_name="Hanna", last_name="Helper")
        Mentor.objects.create(name="Hanna", dojo=self.dojo, role=Mentor.VOLUNTEER, helper_account=self.helper)
        self.event = Event.objects.create(
            name="Session", dojo=self.dojo, status=Event.DRAFT,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10
        )
        self.registration = Registration.objects.create(
            event=self.event, participant=Participant.objects.create(name="Mila"), waiting_list=False, position=1
        )

    def _kw(self, **extra):
        return {"dojo_id": self.dojo.id, **extra}

    def _page_urls(self):
        event_kw = self._kw(event_id=self.event.id)
        return {
            "dashboard": reverse("dojo_dashboard", kwargs=self._kw()),
            "events": reverse("dojo_event_list", kwargs=self._kw()),
            "settings": reverse("dojo_manage", kwargs=self._kw()),
            "create": reverse("dojo_event_create", kwargs=self._kw()),
            "detail": reverse("dojo_event_detail", kwargs=event_kw),
            "attendance": reverse("dojo_event_attendance", kwargs=event_kw),
        }

    def test_helper_can_open_every_admin_page(self):
        self.client.force_login(self.helper)
        for name, url in self._page_urls().items():
            with self.subTest(page=name):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_helper_can_change_status_and_mark_attendance(self):
        self.client.force_login(self.helper)

        self.client.post(reverse("dojo_event_set_status", kwargs=self._kw(event_id=self.event.id)), {"status": Event.OPEN})
        self.client.post(
            reverse("dojo_event_attendance_mark", kwargs=self._kw(event_id=self.event.id, registration_id=self.registration.id)),
            {"attended": "present"},
        )

        self.event.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertEqual(self.event.status, Event.OPEN)
        self.assertTrue(self.registration.attended)

    def test_sidebar_shows_helper_role_and_name(self):
        self.client.force_login(self.helper)

        response = self.client.get(reverse("dojo_dashboard", kwargs=self._kw()))

        self.assertEqual(response.context["dojo_access"].role, access.HELPER)
        self.assertContains(response, '<p class="cd-admin-nav__brand-role caption">Helper</p>', html=True)
        self.assertContains(response, "Hanna Helper")

    def test_owner_sees_owner_role(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dojo_dashboard", kwargs=self._kw()))
        self.assertEqual(response.context["dojo_access"].role, access.OWNER)
        self.assertContains(response, '<p class="cd-admin-nav__brand-role caption">Owner</p>', html=True)

    def test_helper_of_another_dojo_gets_404(self):
        other_dojo = Dojo.objects.create(name="Antwerp")
        self.client.force_login(self.helper)
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": other_dojo.id}))
        self.assertEqual(response.status_code, 404)

    def test_helper_at_several_dojos_can_open_and_switch_between_each(self):
        """Same flexibility as an owner of several dojos: one Mentor profile
        per dojo, each opening that dojo's admin area."""
        antwerp = Dojo.objects.create(name="Antwerp", owner=DojoOwner.objects.create(username="owner2"))
        Mentor.objects.create(name="Hanna", dojo=antwerp, role=Mentor.VOLUNTEER, helper_account=self.helper)
        self.client.force_login(self.helper)

        ghent_page = self.client.get(reverse("dojo_dashboard", kwargs=self._kw()))
        antwerp_page = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))

        self.assertEqual(ghent_page.status_code, 200)
        self.assertEqual(antwerp_page.status_code, 200)
        self.assertEqual(antwerp_page.context["dojo_access"].role, access.HELPER)
        self.assertContains(ghent_page, "data-cd-adminnav-switcher")
        self.assertContains(ghent_page, reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))
        self.assertEqual(list(access.accessible_dojos(self.helper)), [antwerp, self.dojo])

    def test_one_profile_per_helper_per_dojo(self):
        with self.assertRaises(IntegrityError):
            Mentor.objects.create(name="Hanna again", dojo=self.dojo, role=Mentor.VOLUNTEER, helper_account=self.helper)

    def test_guardian_linked_mentor_gets_no_access(self):
        """Only HelperAccount counts — guardians never went through the
        background-check pipeline."""
        guardian = Guardian.objects.create(username="parent1")
        Mentor.objects.create(name="Parent", dojo=self.dojo, role=Mentor.VOLUNTEER, guardian_account=guardian)
        self.client.force_login(guardian)
        response = self.client.get(reverse("dojo_dashboard", kwargs=self._kw()))
        self.assertEqual(response.status_code, 404)

    def test_switcher_lists_owned_and_helped_dojos(self):
        """One account that owns one dojo and helps at another can switch
        between both, with the right role shown on each."""
        antwerp = Dojo.objects.create(name="Antwerp", owner=DojoOwner.objects.create(username="owner2"))
        bruges_owner = DojoOwner.objects.create(username="both")
        bruges = Dojo.objects.create(name="Bruges", owner=bruges_owner)
        as_helper = attach_role(bruges_owner, HelperAccount)
        Mentor.objects.create(name="Both", dojo=antwerp, role=Mentor.VOLUNTEER, helper_account=as_helper)
        self.client.force_login(bruges_owner)

        bruges_page = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": bruges.id}))
        antwerp_page = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))

        self.assertContains(bruges_page, "data-cd-adminnav-switcher")
        self.assertContains(bruges_page, reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))
        self.assertNotContains(bruges_page, reverse("dojo_dashboard", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(bruges_page.context["dojo_access"].role, access.OWNER)
        self.assertEqual(antwerp_page.context["dojo_access"].role, access.HELPER)

    def test_restricted_helper_is_blocked_from_each_capability(self):
        """With every capability removed, a helper keeps the dashboard and
        events list (read-only) but gets a 403 everywhere else, and the
        sidebar/buttons for those capabilities are hidden."""
        self.client.force_login(self.helper)
        urls = self._page_urls()
        event_kw = self._kw(event_id=self.event.id)
        with patch.dict(access.ROLE_CAPABILITIES, {access.HELPER: frozenset()}):
            for name in ("settings", "create", "detail", "attendance"):
                with self.subTest(page=name):
                    self.assertEqual(self.client.get(urls[name]).status_code, 403)
            self.assertEqual(
                self.client.post(reverse("dojo_event_set_status", kwargs=event_kw), {"status": Event.OPEN}).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    reverse("dojo_event_attendance_mark", kwargs=self._kw(event_id=self.event.id, registration_id=self.registration.id)),
                    {"attended": "present"},
                ).status_code,
                403,
            )
            self.assertEqual(self.client.post(reverse("dojo_event_attendance_mark_all", kwargs=event_kw)).status_code, 403)

            dashboard = self.client.get(urls["dashboard"])
            events = self.client.get(urls["events"])

        self.assertEqual(dashboard.status_code, 200)
        self.assertNotContains(dashboard, urls["settings"])
        self.assertNotContains(dashboard, urls["create"])
        self.assertNotContains(dashboard, "Mark all present")
        self.assertContains(dashboard, "Not marked")
        self.assertEqual(events.status_code, 200)
        self.assertNotContains(events, urls["detail"])
        self.assertNotContains(events, urls["attendance"])
        self.event.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertEqual(self.event.status, Event.DRAFT)
        self.assertIsNone(self.registration.attended)

    def test_single_capability_can_be_removed(self):
        self.client.force_login(self.helper)
        restricted = access.ALL_CAPABILITIES - {access.EDIT_SETTINGS}
        with patch.dict(access.ROLE_CAPABILITIES, {access.HELPER: restricted}):
            self.assertEqual(self.client.get(self._page_urls()["settings"]).status_code, 403)
            self.assertEqual(self.client.get(self._page_urls()["create"]).status_code, 200)

    def test_owner_unaffected_by_helper_restrictions(self):
        self.client.force_login(self.owner)
        with patch.dict(access.ROLE_CAPABILITIES, {access.HELPER: frozenset()}):
            self.assertEqual(self.client.get(self._page_urls()["settings"]).status_code, 200)

    def test_nav_offers_helping_at_another_dojo(self):
        self.client.force_login(self.helper)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Help at another dojo")
        self.assertContains(response, reverse("register_helper"))

    def test_nav_manage_link_and_login_redirect_go_to_helpers_dojo(self):
        dashboard_url = reverse("dojo_dashboard", kwargs=self._kw())
        self.client.force_login(self.helper)

        self.assertContains(self.client.get(reverse("home")), dashboard_url)
        self.assertRedirects(self.client.get(reverse("login")), dashboard_url)


class NotificationBellTests(TestCase):
    """The bell's real-data wiring (dojos._notification_context, rendered
    via dojos/templates/dojos/partials/_notification_bell.html) — see
    notifications.tests for notify() itself and NotificationConsumerTests
    below for the live-push side."""

    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1", email="owner@example.com")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)
        self.other_dojo = Dojo.objects.create(name="Antwerp", owner=self.owner)

    def test_dashboard_only_shows_this_dojos_notifications(self):
        notify(self.owner, "About Ghent", dojo=self.dojo)
        notify(self.owner, "About Antwerp", dojo=self.other_dojo)
        self.client.force_login(self.owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": self.dojo.id}))

        self.assertContains(response, "About Ghent")
        self.assertNotContains(response, "About Antwerp")
        self.assertEqual(response.context["unread_count"], 1)

    def test_empty_state(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": self.dojo.id}))
        self.assertContains(response, "You're all caught up.")

    def test_another_recipients_notifications_never_show(self):
        other_owner = DojoOwner.objects.create(username="owner2")
        notify(other_owner, "Not yours", dojo=self.dojo)
        self.client.force_login(self.owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": self.dojo.id}))

        self.assertNotContains(response, "Not yours")


class MarkAllNotificationsReadTests(TestCase):
    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)
        self.other_dojo = Dojo.objects.create(name="Antwerp", owner=self.owner)

    def test_marks_only_this_dojos_unread_notifications_read(self):
        n1 = notify(self.owner, "One", dojo=self.dojo)
        n2 = notify(self.owner, "Two", dojo=self.dojo)
        other_dojo_notification = notify(self.owner, "Elsewhere", dojo=self.other_dojo)
        self.client.force_login(self.owner)

        response = self.client.post(reverse("mark_all_notifications_read", kwargs={"dojo_id": self.dojo.id}))

        self.assertEqual(response.status_code, 200)
        n1.refresh_from_db()
        n2.refresh_from_db()
        other_dojo_notification.refresh_from_db()
        self.assertTrue(n1.read)
        self.assertTrue(n2.read)
        self.assertFalse(other_dojo_notification.read)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse("mark_all_notifications_read", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        other_owner = DojoOwner.objects.create(username="owner2")
        self.client.force_login(other_owner)
        response = self.client.post(reverse("mark_all_notifications_read", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 404)


class OpenNotificationViewTests(TestCase):
    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)

    def test_marks_read_and_redirects_to_its_url(self):
        notification = notify(self.owner, "Something", url="/somewhere/specific/", dojo=self.dojo)
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("open_notification", kwargs={"dojo_id": self.dojo.id, "notification_id": notification.id})
        )

        self.assertRedirects(response, "/somewhere/specific/", fetch_redirect_response=False)
        notification.refresh_from_db()
        self.assertTrue(notification.read)

    def test_blank_url_falls_back_to_the_dashboard(self):
        notification = notify(self.owner, "Something", dojo=self.dojo)
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("open_notification", kwargs={"dojo_id": self.dojo.id, "notification_id": notification.id})
        )

        self.assertRedirects(response, reverse("dojo_dashboard", kwargs={"dojo_id": self.dojo.id}))

    def test_another_recipients_notification_is_404_even_for_the_dojo_owner(self):
        """Read state is per-recipient — one owner must not be able to mark
        a co-owner's copy of a dojo-level notification read, even though
        they both legitimately manage this dojo."""
        other_owner = DojoOwner.objects.create(username="owner2")
        notification = notify(other_owner, "Not yours", dojo=self.dojo)
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("open_notification", kwargs={"dojo_id": self.dojo.id, "notification_id": notification.id})
        )

        self.assertEqual(response.status_code, 404)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNEL_LAYERS)
class NotificationConsumerTests(TransactionTestCase):
    """notifications.consumers.NotificationConsumer — the live-push side of
    the bell. Uses channels' InMemoryChannelLayer instead of the real
    Redis-backed one (website.settings.CHANNEL_LAYERS) so these don't need
    an actual Redis running, same reasoning as notifications.tests'
    fail-open coverage for notify() itself.

    TransactionTestCase, not TestCase: the consumer's DB access
    (database_sync_to_async) runs on a separate thread with its own
    connection, which a TestCase's wrapping transaction (held open on the
    main thread's connection) is invisible to — setUp()'s owner/dojo rows
    would simply not exist as far as that thread's connection is
    concerned. TransactionTestCase commits for real instead, so every
    thread sees the same data (and resets via truncation between tests,
    which is why it's the documented choice for Channels consumer tests
    that touch the database)."""

    def setUp(self):
        self.owner = DojoOwner.objects.create(username="owner1")
        self.dojo = Dojo.objects.create(name="Ghent", owner=self.owner)

    async def test_owner_connection_is_accepted(self):
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), f"/ws/dojos/{self.dojo.id}/notifications/"
        )
        communicator.scope["url_route"] = {"kwargs": {"dojo_id": self.dojo.id}}
        communicator.scope["user"] = self.owner
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_helper_connection_is_accepted(self):
        helper = await sync_to_async(HelperAccount.objects.create)(username="helper1")
        await sync_to_async(Mentor.objects.create)(
            name="Helper", dojo=self.dojo, role=Mentor.VOLUNTEER, helper_account=helper
        )
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), f"/ws/dojos/{self.dojo.id}/notifications/"
        )
        communicator.scope["url_route"] = {"kwargs": {"dojo_id": self.dojo.id}}
        communicator.scope["user"] = helper
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_non_owner_connection_is_refused(self):
        other_owner = await sync_to_async(DojoOwner.objects.create)(username="owner2")
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), f"/ws/dojos/{self.dojo.id}/notifications/"
        )
        communicator.scope["url_route"] = {"kwargs": {"dojo_id": self.dojo.id}}
        communicator.scope["user"] = other_owner
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_notify_pushes_a_rendered_fragment_to_the_open_connection(self):
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), f"/ws/dojos/{self.dojo.id}/notifications/"
        )
        communicator.scope["url_route"] = {"kwargs": {"dojo_id": self.dojo.id}}
        communicator.scope["user"] = self.owner
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await sync_to_async(notify)(self.owner, "Pushed live", dojo=self.dojo)

        message = await communicator.receive_from()
        self.assertIn("Pushed live", message)
        self.assertIn('id="notif-admin-page"', message)
        self.assertIn("hx-swap-oob", message)

        await communicator.disconnect()


class TeamMemberDetailViewTests(TestCase):
    def test_board_member_renders(self):
        mentor = Mentor.objects.create(name="Board Person", role=Mentor.BOARD, dojo=None)
        response = self.client.get(reverse("team_member_detail", kwargs={"mentor_id": mentor.id}))
        self.assertEqual(response.status_code, 200)

    def test_dojo_scoped_mentor_is_404(self):
        """Dojo-scoped mentors only have a detail page via dojo_team.html,
        not this route — see the view's docstring."""
        dojo = Dojo.objects.create(name="Ghent")
        mentor = Mentor.objects.create(name="Ninja", role=Mentor.NINJA, dojo=dojo)
        response = self.client.get(reverse("team_member_detail", kwargs={"mentor_id": mentor.id}))
        self.assertEqual(response.status_code, 404)
