from datetime import date, datetime, time, timedelta
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

from accounts.models import Ninja, User
from content.models import OrganisationTeamMember
from core.testing import TempMediaMixin
from events.models import Event, Registration
from geo.models import AdministrativeBoundary
from notifications.consumers import NotificationConsumer
from notifications.services import notify

from . import access, team
from .models import Dojo, DojoMembership
from .testing import add_member, make_champion, make_dojo, make_mentor

IN_MEMORY_CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


class DojoListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_dojo("Ghent", location=Point(3.7174, 51.0543, srid=4326))
        make_dojo("Antwerp", location=Point(4.4025, 51.2194, srid=4326))

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
        make_dojo("Ghent", location=Point(3.7174, 51.0543, srid=4326))
        response = self.client.get(reverse("dojo_finder_widget"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/partials/_dojo_finder_widget_results.html")


class DojoDetailViewTests(TestCase):
    def test_existing_dojo_renders(self):
        dojo = make_dojo("Ghent")
        response = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": dojo.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dojo"], dojo)

    def test_missing_dojo_is_404(self):
        response = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": 999999}))
        self.assertEqual(response.status_code, 404)


class DojoTeamViewTests(TestCase):
    def test_lists_champion_first_then_mentors_and_youth_mentors(self):
        owner = make_champion(username="owner1", first_name="Zoe")
        dojo = make_dojo("Ghent", champion=owner)
        # "Aaron" sorts before "Zoe" — the champion still comes first.
        add_member(dojo, make_mentor(username="m1", first_name="Aaron"))
        add_member(dojo, User.objects.create(username="kid", first_name="Kid", account_type=User.NINJA),
                   DojoMembership.YOUTH_MENTOR)

        response = self.client.get(reverse("dojo_team", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.status_code, 200)
        roles = [m.role for m in response.context["mentors"]]
        self.assertEqual(roles, [DojoMembership.CHAMPION, DojoMembership.MENTOR, DojoMembership.YOUTH_MENTOR])
        self.assertEqual(response.context["mentors"][0].user_id, owner.pk)

    def test_hides_opted_out_requested_and_former_members(self):
        dojo = make_dojo("Ghent")
        add_member(dojo, make_mentor(username="shy", show_on_team_pages=False))
        add_member(dojo, make_mentor(username="asking"), status=DojoMembership.REQUESTED)
        add_member(dojo, make_mentor(username="gone"), status=DojoMembership.DORMANT)

        response = self.client.get(reverse("dojo_team", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(list(response.context["mentors"]), [])

    def test_profile_is_shared_across_dojos(self):
        mentor = make_mentor(username="m1", first_name="Ann", last_name="Lee", title="Teacher")
        for name in ("Ghent", "Antwerp"):
            dojo = make_dojo(name)
            add_member(dojo, mentor)
            response = self.client.get(reverse("dojo_team", kwargs={"dojo_id": dojo.id}))
            self.assertContains(response, "Ann Lee")
            self.assertContains(response, "Teacher")


class PublicDojoVisibilityTests(TestCase):
    """Only `active` dojos (and their events) are public — draft, dormant
    and archived ones are hidden from the finder and their own pages."""

    def test_non_active_dojo_pages_are_404(self):
        for status in (Dojo.DRAFT, Dojo.DORMANT, Dojo.ARCHIVED):
            with self.subTest(status=status):
                dojo = make_dojo(f"Dojo {status}", status=status)
                self.assertEqual(self.client.get(reverse("dojo_detail", kwargs={"dojo_id": dojo.id})).status_code, 404)
                self.assertEqual(self.client.get(reverse("dojo_team", kwargs={"dojo_id": dojo.id})).status_code, 404)

    def test_finder_lists_active_dojos_only(self):
        make_dojo("Live", location=Point(3.72, 51.05, srid=4326))
        make_dojo("Sleeping", status=Dojo.DORMANT, location=Point(3.72, 51.05, srid=4326))
        cache.clear()

        response = self.client.get(reverse("dojo_list"))

        self.assertEqual([d.name for d in response.context["dojos"]], ["Live"])

    def test_events_of_non_active_dojos_are_hidden(self):
        dojo = make_dojo("Sleeping", status=Dojo.DORMANT)
        event = Event.objects.create(
            name="Session", dojo=dojo, status=Event.OPEN,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10,
        )
        self.assertFalse(Event.objects.visible().filter(id=event.id).exists())
        self.assertEqual(self.client.get(reverse("event_detail", kwargs={"event_id": event.id})).status_code, 404)

    def test_new_dojo_defaults_to_draft(self):
        self.assertEqual(Dojo.objects.create(name="New").status, Dojo.DRAFT)


class DojoMembershipRulesTests(TestCase):
    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)

    def test_only_one_active_champion(self):
        other = DojoMembership(dojo=self.dojo, user=make_champion(username="owner2"),
                               role=DojoMembership.CHAMPION, status=DojoMembership.ACTIVE)
        with self.assertRaises(ValidationError):
            other.clean()

    def test_youth_mentor_must_be_a_ninja_account(self):
        adult = DojoMembership(dojo=self.dojo, user=User.objects.create(username="adult"),
                               role=DojoMembership.YOUTH_MENTOR)
        with self.assertRaises(ValidationError):
            adult.clean()

    def test_ninja_account_can_only_be_youth_mentor(self):
        kid = DojoMembership(dojo=self.dojo, user=User.objects.create(username="kid", account_type=User.NINJA),
                             role=DojoMembership.MENTOR)
        with self.assertRaises(ValidationError):
            kid.clean()

    def test_youth_mentor_promoted_by_another_dojos_team_is_invalid(self):
        elsewhere = make_dojo("Antwerp", champion=make_champion(username="owner2"))
        kid = DojoMembership(dojo=self.dojo, user=User.objects.create(username="kid", account_type=User.NINJA),
                             role=DojoMembership.YOUTH_MENTOR, promoted_by=elsewhere.champion_membership)
        with self.assertRaises(ValidationError):
            kid.clean()

    def test_one_membership_per_account_per_dojo(self):
        with self.assertRaises(IntegrityError):
            add_member(self.dojo, self.owner)

    def test_former_member_stays_on_past_event_teams(self):
        mentor = add_member(self.dojo, make_mentor(username="m1"))
        event = Event.objects.create(
            name="Past", dojo=self.dojo, start_time="2020-01-01T10:00:00Z", end_time="2020-01-01T12:00:00Z", places=10,
        )
        event.team.add(mentor)

        team.leave(mentor)

        mentor.refresh_from_db()
        self.assertEqual(mentor.status, DojoMembership.DORMANT)
        self.assertEqual(list(event.team.all()), [mentor])
        self.assertEqual(mentor.sessions_run, 1)

class DojoDashboardViewTests(TestCase):
    def test_dojo_with_no_sessions_still_renders(self):
        owner = make_champion(username="owner1")
        dojo = make_dojo("Ghent", champion=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["session"])

    def test_shows_real_registrations_for_next_session(self):
        owner = make_champion(username="owner1")
        dojo = make_dojo("Ghent", champion=owner)
        event = Event.objects.create(
            name="Session", dojo=dojo, status=Event.OPEN,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10
        )
        registration = Registration.objects.create(
            event=event, ninja=Ninja.objects.create(name="Mila"), waiting_list=False,
            position=1, attended=True,
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.context["session"], event)
        self.assertEqual(response.context["registrations"], [registration])
        self.assertContains(response, "Mila")
        self.assertContains(response, "1 of 1 present")

    def test_missing_dojo_is_404(self):
        owner = make_champion(username="owner1")
        self.client.force_login(owner)
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": 999999}))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_redirected_to_login(self):
        dojo = make_dojo("Ghent")
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        owner = make_champion(username="owner1")
        other_owner = make_champion(username="owner2")
        dojo = make_dojo("Ghent", champion=owner)
        self.client.force_login(other_owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.status_code, 404)


class DojoManageViewTests(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner, address="Oude Vismijn 3, Ghent")

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
        other_owner = make_champion(username="owner2")
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
        self.assertEqual(self.dojo.icon.name, "library/dojos/icon-02-robot.svg")

    def test_template_icon_is_linked_not_copied(self):
        """Two dojos picking the same template icon share the one library
        file, and the edit form preselects it."""
        other = make_dojo("Antwerp", champion=make_champion(username="owner2"))
        self.client.force_login(self.owner)
        self.client.post(
            reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(template_icon="icon-02-robot.svg"),
        )
        self.client.force_login(other.champion)
        self.client.post(
            reverse("dojo_manage", kwargs={"dojo_id": other.id}),
            self._valid_post_data(name="CoderDojo Antwerp", template_icon="icon-02-robot.svg"),
        )

        other.refresh_from_db()
        self.assertEqual(other.icon.name, "library/dojos/icon-02-robot.svg")
        self.assertEqual(list((self.media_root / "library" / "dojos").iterdir()), [self.media_root / "library/dojos/icon-02-robot.svg"])
        self.assertFalse((self.media_root / "dojos").exists())
        response = self.client.get(reverse("dojo_manage", kwargs={"dojo_id": other.id}))
        self.assertEqual(response.context["form"]["template_icon"].value(), "icon-02-robot.svg")

    def test_uploaded_icon_gets_its_own_copy(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        png = io.BytesIO()
        Image.new("RGB", (4, 4)).save(png, "PNG")
        self.client.force_login(self.owner)
        upload = SimpleUploadedFile("mine.png", png.getvalue(), content_type="image/png")
        self.client.post(
            reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}),
            {**self._valid_post_data(template_icon="icon-02-robot.svg"), "icon": upload},
        )

        self.dojo.refresh_from_db()
        self.assertTrue(self.dojo.icon.name.startswith("dojos/"), self.dojo.icon.name)


class DojoEventListViewTests(TestCase):
    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        other_owner = make_champion(username="owner2")
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


class DojoEventCreateViewTests(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)

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
            "team": [],
        }
        data.update(overrides)
        return data

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        other_owner = make_champion(username="owner2")
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

    def test_team_choices_are_this_dojos_active_team(self):
        """Anyone active on this dojo's team — including the champion
        themselves — can be put on a session; other dojos' members, requested
        and former members can't."""
        add_member(make_dojo("Antwerp"), make_mentor(username="elsewhere"))
        own_mentor = add_member(self.dojo, make_mentor(username="own"))
        add_member(self.dojo, make_mentor(username="asking"), status=DojoMembership.REQUESTED)
        add_member(self.dojo, make_mentor(username="gone"), status=DojoMembership.DORMANT)
        self.client.force_login(self.owner)

        response = self.client.get(reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}))

        self.assertEqual(
            set(response.context["form"].fields["team"].queryset), {own_mentor, self.dojo.champion_membership},
        )

    def test_several_team_members_can_be_assigned(self):
        mentor_a = add_member(self.dojo, make_mentor(username="a"))
        mentor_b = add_member(self.dojo, make_mentor(username="b"))
        self.client.force_login(self.owner)

        self.client.post(
            reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(team=[str(mentor_a.id), str(mentor_b.id)]),
        )

        event = Event.objects.get(dojo=self.dojo)
        self.assertEqual(set(event.team.all()), {mentor_a, mentor_b})

    def test_template_image_used_when_no_file_uploaded(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}),
            self._valid_post_data(template_image="coding-saturday.svg"),
        )

        self.assertRedirects(response, reverse("dojo_event_list", kwargs={"dojo_id": self.dojo.id}))
        event = Event.objects.get(dojo=self.dojo)
        self.assertEqual(event.image.name, "library/events/coding-saturday.svg")


class DojoEventDetailViewTests(TestCase):
    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
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
            "team": [],
        }
        data.update(overrides)
        return data

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_another_owner_gets_404(self):
        other_owner = make_champion(username="owner2")
        self.client.force_login(other_owner)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 404)

    def test_event_of_another_dojo_gets_404(self):
        """Owning *a* dojo isn't enough — the event must belong to the dojo
        in the URL, or an owner could edit any event by swapping ids."""
        other_dojo = make_dojo("Antwerp")
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
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
        self.event = Event.objects.create(
            name="Session", dojo=self.dojo, status=Event.OPEN,
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        self.zoe = Registration.objects.create(
            event=self.event, ninja=Ninja.objects.create(name="Zoe"), waiting_list=False, position=1
        )
        self.anna = Registration.objects.create(
            event=self.event, ninja=Ninja.objects.create(name="Anna"), waiting_list=False, position=2
        )
        self.waitlisted = Registration.objects.create(
            event=self.event, ninja=Ninja.objects.create(name="Waitlisted"), waiting_list=True, position=3
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
        other_owner = make_champion(username="owner2")
        self.client.force_login(other_owner)
        self.assertEqual(self.client.get(self._page_url()).status_code, 404)
        self.assertEqual(self.client.post(self._mark_url(self.zoe), {"attended": "present"}).status_code, 404)
        self.assertEqual(self.client.post(self._mark_all_url()).status_code, 404)
        self.zoe.refresh_from_db()
        self.assertIsNone(self.zoe.attended)

    def test_event_of_another_dojo_gets_404(self):
        other_event = Event.objects.create(
            name="Elsewhere", dojo=make_dojo("Antwerp"),
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self._page_url(other_event)).status_code, 404)

    def test_registration_of_another_event_gets_404(self):
        """The registration id must belong to the event in the URL, or an
        owner could mark attendance on another dojo's session."""
        other_event = Event.objects.create(
            name="Elsewhere", dojo=make_dojo("Antwerp"),
            start_time="2030-01-01T10:00:00Z", end_time="2030-01-01T12:00:00Z", places=10
        )
        other_registration = Registration.objects.create(
            event=other_event, ninja=Ninja.objects.create(name="Other"), waiting_list=False, position=1
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
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
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
        other_owner = make_champion(username="owner2")
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
        ninja = Ninja.objects.create(name="Kid")
        Registration.objects.create(event=self.event, ninja=ninja, waiting_list=False, position=1)
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
        owner = make_champion(username="owner1")
        dojo = make_dojo("Ghent", champion=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertNotContains(response, "data-cd-adminnav-switcher")
        self.assertContains(response, "Ghent")

    def test_multi_dojo_owner_sees_switcher_listing_every_dojo(self):
        owner = make_champion(username="owner1")
        ghent = make_dojo("Ghent", champion=owner)
        antwerp = make_dojo("Antwerp", champion=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": ghent.id}))

        self.assertContains(response, "data-cd-adminnav-switcher")
        self.assertContains(response, "Ghent")
        self.assertContains(response, "Antwerp")
        # The switch-target link for the *other* dojo stays on the same
        # screen (Attendance here) rather than always landing on one page.
        self.assertContains(response, reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))

    def test_switch_links_go_to_manage_when_on_settings(self):
        owner = make_champion(username="owner1")
        ghent = make_dojo("Ghent", champion=owner)
        antwerp = make_dojo("Antwerp", champion=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_manage", kwargs={"dojo_id": ghent.id}))

        self.assertContains(response, reverse("dojo_manage", kwargs={"dojo_id": antwerp.id}))

    def test_dojos_owned_by_someone_else_are_not_listed(self):
        owner = make_champion(username="owner1")
        other_owner = make_champion(username="owner2")
        dojo = make_dojo("Ghent", champion=owner)
        make_dojo("Antwerp", champion=other_owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertNotContains(response, "data-cd-adminnav-switcher")
        self.assertNotContains(response, "Antwerp")


class HelperDojoAccessTests(TestCase):
    """An active mentor membership (dojos.DojoMembership) gets the dojo's
    admin area (dojos.access) — with every capability a champion has except
    the dojo's lifecycle, and each one can be taken away via
    ROLE_CAPABILITIES."""

    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
        self.helper = make_mentor(username="helper1", first_name="Hanna", last_name="Helper")
        add_member(self.dojo, self.helper)
        self.event = Event.objects.create(
            name="Session", dojo=self.dojo, status=Event.DRAFT,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10
        )
        self.registration = Registration.objects.create(
            event=self.event, ninja=Ninja.objects.create(name="Mila"), waiting_list=False, position=1
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

        self.assertEqual(response.context["dojo_access"].role, access.MENTOR)
        self.assertContains(response, '<p class="cd-admin-nav__brand-role caption">Mentor</p>', html=True)
        self.assertContains(response, "Hanna Helper")

    def test_owner_sees_owner_role(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dojo_dashboard", kwargs=self._kw()))
        self.assertEqual(response.context["dojo_access"].role, access.CHAMPION)
        self.assertContains(response, '<p class="cd-admin-nav__brand-role caption">Champion</p>', html=True)

    def test_helper_of_another_dojo_gets_404(self):
        other_dojo = make_dojo("Antwerp")
        self.client.force_login(self.helper)
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": other_dojo.id}))
        self.assertEqual(response.status_code, 404)

    def test_helper_at_several_dojos_can_open_and_switch_between_each(self):
        """Same flexibility as an owner of several dojos: one membership per
        dojo, each opening that dojo's admin area."""
        antwerp = make_dojo("Antwerp", champion=make_champion(username="owner2"))
        add_member(antwerp, self.helper)
        self.client.force_login(self.helper)

        ghent_page = self.client.get(reverse("dojo_dashboard", kwargs=self._kw()))
        antwerp_page = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))

        self.assertEqual(ghent_page.status_code, 200)
        self.assertEqual(antwerp_page.status_code, 200)
        self.assertEqual(antwerp_page.context["dojo_access"].role, access.MENTOR)
        self.assertContains(ghent_page, "data-cd-adminnav-switcher")
        self.assertContains(ghent_page, reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))
        self.assertEqual(list(access.accessible_dojos(self.helper)), [antwerp, self.dojo])

    def test_one_profile_per_helper_per_dojo(self):
        with self.assertRaises(IntegrityError):
            add_member(self.dojo, self.helper)

    def test_youth_mentor_gets_no_admin_access(self):
        """Youth mentors are ninjas: on the team, never in the admin area
        (it shows other children's details)."""
        kid = User.objects.create(username="kid", account_type=User.NINJA)
        add_member(self.dojo, kid, DojoMembership.YOUTH_MENTOR)
        self.client.force_login(kid)
        response = self.client.get(reverse("dojo_dashboard", kwargs=self._kw()))
        self.assertEqual(response.status_code, 404)

    def test_requested_or_former_membership_gets_no_access(self):
        for status in (DojoMembership.REQUESTED, DojoMembership.DORMANT):
            with self.subTest(status=status):
                user = make_mentor(username=f"u-{status}")
                add_member(self.dojo, user, status=status)
                self.client.force_login(user)
                response = self.client.get(reverse("dojo_dashboard", kwargs=self._kw()))
                self.assertEqual(response.status_code, 404)

    def test_mentor_with_lapsed_check_gets_no_access(self):
        self.helper.background_check_expires_at = timezone.now() - timedelta(days=1)
        self.helper.save(update_fields=["background_check_expires_at"])
        self.assertIsNone(access.dojo_role(self.helper, self.dojo))
        self.assertEqual(list(access.accessible_dojos(self.helper)), [])

    def test_mentor_cannot_manage_the_dojo_lifecycle(self):
        self.client.force_login(self.helper)
        response = self.client.post(
            reverse("dojo_set_lifecycle", kwargs=self._kw()), {"action": "archive"},
        )
        self.assertEqual(response.status_code, 403)
        self.dojo.refresh_from_db()
        self.assertEqual(self.dojo.status, Dojo.ACTIVE)

    def test_switcher_lists_owned_and_helped_dojos(self):
        """One account that owns one dojo and helps at another can switch
        between both, with the right role shown on each."""
        antwerp = make_dojo("Antwerp", champion=make_champion(username="owner2"))
        bruges_owner = make_champion(username="both")
        bruges = make_dojo("Bruges", champion=bruges_owner)
        # One account: champion of Bruges, mentor at Antwerp — no second login.
        add_member(antwerp, bruges_owner)
        self.client.force_login(bruges_owner)

        bruges_page = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": bruges.id}))
        antwerp_page = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))

        self.assertContains(bruges_page, "data-cd-adminnav-switcher")
        self.assertContains(bruges_page, reverse("dojo_dashboard", kwargs={"dojo_id": antwerp.id}))
        self.assertNotContains(bruges_page, reverse("dojo_dashboard", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(bruges_page.context["dojo_access"].role, access.CHAMPION)
        self.assertEqual(antwerp_page.context["dojo_access"].role, access.MENTOR)

    def test_restricted_helper_is_blocked_from_each_capability(self):
        """With every capability removed, a helper keeps the dashboard and
        events list (read-only) but gets a 403 everywhere else, and the
        sidebar/buttons for those capabilities are hidden."""
        self.client.force_login(self.helper)
        urls = self._page_urls()
        event_kw = self._kw(event_id=self.event.id)
        with patch.dict(access.ROLE_CAPABILITIES, {access.MENTOR: frozenset()}):
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
        # Exact hrefs: the Team page lives under /manage/team/, so a plain
        # substring check for the settings URL would match that link too.
        self.assertNotContains(dashboard, f'href="{urls["settings"]}"')
        self.assertNotContains(dashboard, f'href="{urls["create"]}"')
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
        with patch.dict(access.ROLE_CAPABILITIES, {access.MENTOR: restricted}):
            self.assertEqual(self.client.get(self._page_urls()["settings"]).status_code, 403)
            self.assertEqual(self.client.get(self._page_urls()["create"]).status_code, 200)

    def test_owner_unaffected_by_helper_restrictions(self):
        self.client.force_login(self.owner)
        with patch.dict(access.ROLE_CAPABILITIES, {access.MENTOR: frozenset()}):
            self.assertEqual(self.client.get(self._page_urls()["settings"]).status_code, 200)

    def test_nav_offers_helping_at_another_dojo(self):
        self.client.force_login(self.helper)
        response = self.client.get(reverse("home"))
        # Approved mentors ask to join from a dojo's own page, so the link
        # goes to the dojo finder rather than a new application.
        self.assertContains(response, "Help at another dojo")
        self.assertContains(response, f'href="{reverse("dojo_list")}"')

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
        self.owner = make_champion(username="owner1", email="owner@example.com")
        self.dojo = make_dojo("Ghent", champion=self.owner)
        self.other_dojo = make_dojo("Antwerp", champion=self.owner)

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
        other_owner = make_champion(username="owner2")
        notify(other_owner, "Not yours", dojo=self.dojo)
        self.client.force_login(self.owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": self.dojo.id}))

        self.assertNotContains(response, "Not yours")


class MarkAllNotificationsReadTests(TestCase):
    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
        self.other_dojo = make_dojo("Antwerp", champion=self.owner)

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
        other_owner = make_champion(username="owner2")
        self.client.force_login(other_owner)
        response = self.client.post(reverse("mark_all_notifications_read", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 404)


class OpenNotificationViewTests(TestCase):
    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)

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
        other_owner = make_champion(username="owner2")
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
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)

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
        helper = await sync_to_async(make_mentor)(username="helper1")
        await sync_to_async(add_member)(self.dojo, helper)
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), f"/ws/dojos/{self.dojo.id}/notifications/"
        )
        communicator.scope["url_route"] = {"kwargs": {"dojo_id": self.dojo.id}}
        communicator.scope["user"] = helper
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_non_owner_connection_is_refused(self):
        other_owner = await sync_to_async(make_champion)(username="owner2")
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
    """The organisation's team details page (content.OrganisationTeamMember,
    display only — e.g. "Member of the board")."""

    def test_listed_member_renders_with_position(self):
        member = OrganisationTeamMember.objects.create(
            name="Board Person", position="Member of the board", focus_areas="Finance, Grants",
        )
        response = self.client.get(reverse("team_member_detail", kwargs={"member_id": member.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member of the board")
        self.assertEqual(response.context["focus_areas"], ["Finance", "Grants"])

    def test_hidden_member_is_404(self):
        member = OrganisationTeamMember.objects.create(name="Hidden", position="Treasurer", is_public=False)
        response = self.client.get(reverse("team_member_detail", kwargs={"member_id": member.id}))
        self.assertEqual(response.status_code, 404)

    def test_homepage_lists_public_members_in_order(self):
        OrganisationTeamMember.objects.create(name="Second", position="Treasurer", order=2)
        OrganisationTeamMember.objects.create(name="First", position="Chair", order=1)
        OrganisationTeamMember.objects.create(name="Hidden", position="Secretary", is_public=False)
        cache.clear()
        response = self.client.get(reverse("home"))
        self.assertEqual([m.name for m in response.context["team"]], ["First", "Second"])


class JoinRequestTests(TestCase):
    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
        self.mentor = make_mentor(username="mentor1", first_name="Mia")
        self.url = reverse("dojo_join_request", kwargs={"dojo_id": self.dojo.id})

    def test_approved_mentor_sees_button_and_can_ask(self):
        self.client.force_login(self.mentor)
        page = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(page.context["join_state"], "can_request")

        with patch("dojos.team.notify") as mock_notify:
            self.client.post(self.url)

        membership = DojoMembership.objects.get(dojo=self.dojo, user=self.mentor)
        self.assertEqual(membership.status, DojoMembership.REQUESTED)
        self.assertEqual({c.args[0].pk for c in mock_notify.call_args_list}, {self.owner.pk})

    def test_plain_account_cannot_ask(self):
        parent = User.objects.create(username="parent")
        self.client.force_login(parent)
        page = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": self.dojo.id}))
        self.assertIsNone(page.context["join_state"])
        self.client.post(self.url)
        self.assertFalse(DojoMembership.objects.filter(user=parent).exists())

    def test_cannot_ask_twice(self):
        self.client.force_login(self.mentor)
        self.client.post(self.url)
        self.client.post(self.url)
        self.assertEqual(DojoMembership.objects.filter(user=self.mentor).count(), 1)

    def test_former_member_rejoins_on_the_same_row(self):
        membership = add_member(self.dojo, self.mentor, status=DojoMembership.DORMANT)
        self.client.force_login(self.mentor)
        self.client.post(self.url)
        membership.refresh_from_db()
        self.assertEqual(membership.status, DojoMembership.REQUESTED)
        self.assertEqual(DojoMembership.objects.filter(user=self.mentor).count(), 1)


class TeamManagementTests(TestCase):
    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
        self.mentor_account = make_mentor(username="mentor1", email="mentor1@example.com")
        self.mentor = add_member(self.dojo, self.mentor_account)
        self.action_url = reverse("dojo_team_action", kwargs={"dojo_id": self.dojo.id})

    def _post(self, user, **data):
        self.client.force_login(user)
        return self.client.post(self.action_url, data)

    def test_team_page_renders_for_team(self):
        self.client.force_login(self.mentor_account)
        response = self.client.get(reverse("dojo_team_manage", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["active_members"]), {self.dojo.champion_membership, self.mentor})

    def test_mentor_can_accept_and_decline_requests(self):
        asking = add_member(self.dojo, make_mentor(username="a"), status=DojoMembership.REQUESTED)
        first_timer = add_member(self.dojo, make_mentor(username="b"), status=DojoMembership.REQUESTED)

        self._post(self.mentor_account, action="accept", membership_id=asking.id)
        self._post(self.mentor_account, action="decline", membership_id=first_timer.id)

        asking.refresh_from_db()
        self.assertEqual(asking.status, DojoMembership.ACTIVE)
        self.assertEqual(asking.decided_by_id, self.mentor_account.pk)
        self.assertIsNotNone(asking.joined_at)
        # A declined first-time request is simply removed.
        self.assertFalse(DojoMembership.objects.filter(id=first_timer.id).exists())

    def test_add_mentor_by_email_requires_an_approved_mentor(self):
        approved = make_mentor(username="c", email="approved@example.com")
        User.objects.create(username="d", email="plain@example.com")

        self._post(self.owner, action="add_mentor", email="approved@example.com")
        self._post(self.owner, action="add_mentor", email="plain@example.com")

        self.assertTrue(self.dojo.memberships.active().filter(user=approved).exists())
        self.assertFalse(self.dojo.memberships.filter(user__email="plain@example.com").exists())

    def test_promote_ninja_to_youth_mentor(self):
        kid_login = User.objects.create(username="kid", account_type=User.NINJA)
        Ninja.objects.create(name="Kid", account=kid_login, home_dojo=self.dojo)
        ninja = Ninja.objects.get(account=kid_login)

        self._post(self.mentor_account, action="promote", ninja_id=ninja.id)

        membership = DojoMembership.objects.get(dojo=self.dojo, user=kid_login)
        self.assertEqual(membership.role, DojoMembership.YOUTH_MENTOR)
        self.assertEqual(membership.promoted_by, self.mentor)

    def test_cannot_promote_a_ninja_unrelated_to_this_dojo(self):
        kid_login = User.objects.create(username="kid", account_type=User.NINJA)
        ninja = Ninja.objects.create(name="Kid", account=kid_login, home_dojo=make_dojo("Elsewhere"))
        response = self._post(self.owner, action="promote", ninja_id=ninja.id)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(DojoMembership.objects.filter(user=kid_login).exists())

    def test_remove_member_goes_dormant_and_champion_cannot_be_removed(self):
        self._post(self.owner, action="remove", membership_id=self.mentor.id)
        self._post(self.mentor_account, action="remove", membership_id=self.dojo.champion_membership.id)

        self.mentor.refresh_from_db()
        self.assertEqual(self.mentor.status, DojoMembership.DORMANT)
        self.assertIsNotNone(self.dojo.champion_membership)

    def test_mentor_can_leave_but_champion_cannot(self):
        response = self._post(self.mentor_account, action="leave")
        self.assertRedirects(response, reverse("account_home"))
        self.mentor.refresh_from_db()
        self.assertEqual(self.mentor.status, DojoMembership.DORMANT)

        self._post(self.owner, action="leave")
        self.assertEqual(self.dojo.champion.pk, self.owner.pk)

    def test_champion_transfers_to_an_active_mentor(self):
        self._post(self.owner, action="transfer", membership_id=self.mentor.id)

        self.assertEqual(self.dojo.champion.pk, self.mentor_account.pk)
        old = DojoMembership.objects.get(dojo=self.dojo, user=self.owner)
        self.assertEqual((old.role, old.status), (DojoMembership.MENTOR, DojoMembership.ACTIVE))

    def test_only_the_champion_can_transfer(self):
        other = add_member(self.dojo, make_mentor(username="e"))
        response = self._post(self.mentor_account, action="transfer", membership_id=other.id)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.dojo.champion.pk, self.owner.pk)

    def test_mentor_without_manage_team_is_blocked(self):
        asking = add_member(self.dojo, make_mentor(username="f"), status=DojoMembership.REQUESTED)
        with patch.dict(access.ROLE_CAPABILITIES, {access.MENTOR: frozenset()}):
            response = self._post(self.mentor_account, action="accept", membership_id=asking.id)
        self.assertEqual(response.status_code, 403)
        asking.refresh_from_db()
        self.assertEqual(asking.status, DojoMembership.REQUESTED)


class DojoLifecycleTests(TestCase):
    def setUp(self):
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner, status=Dojo.DRAFT)
        self.url = reverse("dojo_set_lifecycle", kwargs={"dojo_id": self.dojo.id})
        self.client.force_login(self.owner)

    def _act(self, action):
        self.client.post(self.url, {"action": action})
        self.dojo.refresh_from_db()
        return self.dojo.status

    def test_full_cycle(self):
        self.assertEqual(self._act("launch"), Dojo.ACTIVE)
        self.assertEqual(self._act("go_dormant"), Dojo.DORMANT)
        self.assertEqual(self._act("restart"), Dojo.ACTIVE)
        self.assertEqual(self._act("archive"), Dojo.ARCHIVED)
        self.assertEqual(self._act("reopen"), Dojo.DRAFT)

    def test_invalid_transition_is_refused(self):
        self.assertEqual(self._act("restart"), Dojo.DRAFT)
        self.assertEqual(self._act("archive"), Dojo.DRAFT)

    def test_dormant_and_archive_blocked_by_active_events(self):
        self._act("launch")
        Event.objects.create(
            name="Upcoming", dojo=self.dojo, status=Event.OPEN,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10,
        )
        self.assertEqual(self._act("go_dormant"), Dojo.ACTIVE)
        self.assertEqual(self._act("archive"), Dojo.ACTIVE)

    def test_closed_or_past_events_do_not_block(self):
        self._act("launch")
        Event.objects.create(
            name="Closed", dojo=self.dojo, status=Event.CLOSED,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10,
        )
        Event.objects.create(
            name="Past", dojo=self.dojo, status=Event.OPEN,
            start_time="2020-01-01T10:00:00Z", end_time="2020-01-01T12:00:00Z", places=10,
        )
        self.assertEqual(self._act("go_dormant"), Dojo.DORMANT)

    def test_going_dormant_auto_declines_pending_requests(self):
        self._act("launch")
        asking = add_member(self.dojo, make_mentor(username="a"), status=DojoMembership.REQUESTED)
        with patch("dojos.team.notify") as mock_notify:
            self._act("go_dormant")
        self.assertFalse(DojoMembership.objects.filter(id=asking.id).exists())
        self.assertIn(asking.user_id, {c.args[0].pk for c in mock_notify.call_args_list})

    def test_dormant_dojo_leaves_the_finder(self):
        self._act("launch")
        self.dojo.location = Point(3.72, 51.05, srid=4326)
        self.dojo.save(update_fields=["location"])
        cache.clear()
        self.assertIn(self.dojo, list(self.client.get(reverse("dojo_list")).context["dojos"]))

        self._act("go_dormant")

        # change_status clears the finder's cached default list itself.
        self.assertNotIn(self.dojo, list(self.client.get(reverse("dojo_list")).context["dojos"]))


class DormancyNudgeTests(TestCase):
    def setUp(self):
        self.dojo = make_dojo("Ghent")

    def _event(self, days_from_now):
        start = timezone.now() + timedelta(days=days_from_now)
        return Event.objects.create(
            name="Session", dojo=self.dojo, start_time=start, end_time=start + timedelta(hours=2), places=10,
        )

    def test_nudged_after_half_a_year_without_events(self):
        self._event(-200)
        self.assertTrue(team.needs_dormancy_nudge(self.dojo))

    def test_not_nudged_with_an_upcoming_event(self):
        self._event(-200)
        self._event(10)
        self.assertFalse(team.needs_dormancy_nudge(self.dojo))

    def test_not_nudged_when_recent_or_never_held_an_event(self):
        self.assertFalse(team.needs_dormancy_nudge(self.dojo))
        self._event(-30)
        self.assertFalse(team.needs_dormancy_nudge(self.dojo))

    def test_dashboard_shows_the_banner(self):
        owner = make_champion(username="owner1")
        add_member(self.dojo, owner, DojoMembership.CHAMPION)
        self._event(-200)
        self.client.force_login(owner)
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": self.dojo.id}))
        self.assertTrue(response.context["dormancy_nudge"])
        self.assertContains(response, "No sessions have been planned for over six months")


class PathwayScopeTests(TestCase):
    """Pathways at three levels, each pre-filled from the one above: dojo
    ("provides") → event ("covers", public) → registration ("works on")."""

    def setUp(self):
        from pathways.models import Pathway

        self.scratch = Pathway.objects.create(name="Scratch")
        self.python = Pathway.objects.create(name="Python")
        self.web = Pathway.objects.create(name="Web")
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
        self.dojo.pathways.set([self.scratch, self.python])
        self.client.force_login(self.owner)

    def _event(self, **fields):
        return Event.objects.create(
            name="Session", dojo=self.dojo, status=Event.OPEN,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10, **fields,
        )

    def test_new_event_preselects_the_dojos_pathways(self):
        response = self.client.get(reverse("dojo_event_create", kwargs={"dojo_id": self.dojo.id}))
        self.assertEqual(set(response.context["form"].fields["pathways"].initial), {self.scratch.id, self.python.id})

    def test_existing_event_keeps_its_own_pathways(self):
        event = self._event()
        event.pathways.set([self.web])
        response = self.client.get(reverse("dojo_event_detail", kwargs={"dojo_id": self.dojo.id, "event_id": event.id}))
        self.assertEqual(list(response.context["form"]["pathways"].value()), [self.web.id])

    def test_settings_save_the_dojos_pathways(self):
        response = self.client.post(
            reverse("dojo_manage", kwargs={"dojo_id": self.dojo.id}),
            {"name": "Ghent", "pathways": [self.web.id], "template_icon": ""},
        )
        self.assertTrue(response.context["saved"], response.context["form"].errors)
        self.assertEqual(list(self.dojo.pathways.all()), [self.web])

    def test_signup_prefills_registration_pathways_from_the_event(self):
        event = self._event()
        event.pathways.set([self.scratch, self.web])
        parent = User.objects.create(username="parent")
        ninja = Ninja.objects.create(name="Mila")
        from accounts.models import Guardianship

        Guardianship.objects.create(guardian=parent, ninja=ninja)
        self.client.force_login(parent)

        self.client.post(reverse("event_signup", kwargs={"event_id": event.id}), {"child": [ninja.id]})

        registration = Registration.objects.get(event=event, ninja=ninja)
        self.assertEqual(set(registration.pathways.all()), {self.scratch, self.web})

    def test_team_narrows_what_a_ninja_works_on(self):
        event = self._event()
        registration = Registration.objects.create(
            event=event, ninja=Ninja.objects.create(name="Mila"), waiting_list=False, position=1,
        )
        registration.pathways.set([self.scratch, self.python])
        url = reverse("dojo_event_registration_pathways", kwargs={
            "dojo_id": self.dojo.id, "event_id": event.id, "registration_id": registration.id,
        })

        # Any pathway may be picked — the event's are only the default.
        response = self.client.post(url, {"pathway": [self.web.id]}, HTTP_HX_REQUEST="true")

        self.assertTemplateUsed(response, "dojos/partials/_attendance_row.html")
        self.assertEqual(list(registration.pathways.all()), [self.web])

    def test_pathway_editing_needs_take_attendance_and_the_right_event(self):
        event = self._event()
        registration = Registration.objects.create(
            event=event, ninja=Ninja.objects.create(name="Mila"), waiting_list=False, position=1,
        )
        mentor = make_mentor(username="m1")
        add_member(self.dojo, mentor)
        url = reverse("dojo_event_registration_pathways", kwargs={
            "dojo_id": self.dojo.id, "event_id": event.id, "registration_id": registration.id,
        })
        self.client.force_login(mentor)
        with patch.dict(access.ROLE_CAPABILITIES, {access.MENTOR: frozenset()}):
            self.assertEqual(self.client.post(url, {"pathway": [self.web.id]}).status_code, 403)

        other_event = Event.objects.create(
            name="Other", dojo=make_dojo("Antwerp"), start_time="2099-01-01T10:00:00Z",
            end_time="2099-01-01T12:00:00Z", places=10,
        )
        wrong = reverse("dojo_event_registration_pathways", kwargs={
            "dojo_id": self.dojo.id, "event_id": other_event.id, "registration_id": registration.id,
        })
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(wrong, {"pathway": [self.web.id]}).status_code, 404)
        self.assertFalse(registration.pathways.exists())

    def test_public_pages_show_pathways(self):
        event = self._event()
        event.pathways.set([self.web])
        self.client.logout()
        self.assertContains(self.client.get(reverse("event_detail", kwargs={"event_id": event.id})), "Pathways this session covers")
        dojo_page = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": self.dojo.id}))
        self.assertContains(dojo_page, "Scratch")
        self.assertContains(dojo_page, "Python")


class AwardBeltViewTests(TestCase):
    """Awarding a belt from the attendance list (AWARD_BELTS), and milestone
    badges following attendance marks."""

    def setUp(self):
        from events.models import Badge, Belt

        self.white = Belt.objects.create(level=1, name="White belt")
        self.yellow = Belt.objects.create(level=2, name="Yellow belt")
        self.band = Badge.objects.create(name="White Band", kind=Badge.MILESTONE, threshold=1)
        self.owner = make_champion(username="owner1")
        self.dojo = make_dojo("Ghent", champion=self.owner)
        self.event = Event.objects.create(
            name="Session", dojo=self.dojo, status=Event.OPEN,
            start_time="2099-01-01T10:00:00Z", end_time="2099-01-01T12:00:00Z", places=10,
        )
        self.ninja = Ninja.objects.create(name="Mila")
        self.registration = Registration.objects.create(event=self.event, ninja=self.ninja, waiting_list=False, position=1)
        self.url = reverse("dojo_event_award_belt", kwargs={
            "dojo_id": self.dojo.id, "event_id": self.event.id, "registration_id": self.registration.id,
        })
        self.client.force_login(self.owner)

    def test_awards_the_belt_and_rerenders_the_row(self):
        response = self.client.post(self.url, {"belt": self.white.id, "note": "Built a game"}, HTTP_HX_REQUEST="true")

        self.assertTemplateUsed(response, "dojos/partials/_attendance_row.html")
        award = self.ninja.belts.get()
        self.assertEqual((award.belt, award.awarded_by, award.note), (self.white, self.owner, "Built a game"))
        self.assertEqual(award.awarded_as_membership, self.dojo.champion_membership)
        # The row now offers only the belts above it.
        self.assertContains(response, "Yellow belt")
        self.assertNotContains(response, f'<option value="{self.white.id}">')

    def test_a_lower_belt_is_refused_with_a_message(self):
        self.client.post(self.url, {"belt": self.yellow.id}, HTTP_HX_REQUEST="true")
        response = self.client.post(self.url, {"belt": self.white.id}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.context["belt_error"], "Mila already has the Yellow belt (or higher).")
        self.assertEqual(self.ninja.belts.count(), 1)

    def test_needs_award_belts_and_the_right_event(self):
        mentor = make_mentor(username="m1")
        add_member(self.dojo, mentor)
        self.client.force_login(mentor)
        with patch.dict(access.ROLE_CAPABILITIES, {access.MENTOR: frozenset({access.TAKE_ATTENDANCE})}):
            self.assertEqual(self.client.post(self.url, {"belt": self.white.id}).status_code, 403)
            page = self.client.get(reverse("dojo_event_attendance", kwargs={"dojo_id": self.dojo.id, "event_id": self.event.id}))
            self.assertNotContains(page, "Award belt")

        other_event = Event.objects.create(
            name="Other", dojo=make_dojo("Antwerp"), start_time="2099-01-01T10:00:00Z",
            end_time="2099-01-01T12:00:00Z", places=10,
        )
        wrong = reverse("dojo_event_award_belt", kwargs={
            "dojo_id": self.dojo.id, "event_id": other_event.id, "registration_id": self.registration.id,
        })
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(wrong, {"belt": self.white.id}).status_code, 404)
        self.assertFalse(self.ninja.belts.exists())

    def test_marking_present_updates_milestone_badges(self):
        mark = reverse("dojo_event_attendance_mark", kwargs={
            "dojo_id": self.dojo.id, "event_id": self.event.id, "registration_id": self.registration.id,
        })
        self.client.post(mark, {"attended": "present"})
        self.assertIsNotNone(self.ninja.badges.get(badge=self.band).earned_date)

    def test_mark_all_present_updates_milestone_badges(self):
        self.client.post(reverse("dojo_event_attendance_mark_all", kwargs={"dojo_id": self.dojo.id, "event_id": self.event.id}))
        self.assertIsNotNone(self.ninja.badges.get(badge=self.band).earned_date)


class DojoUpdatesTests(TestCase):
    """The admin "Updates" page (dojo_updates / dojo_update_delete) and the
    public page's "From this dojo" list."""

    def setUp(self):
        from content.models import Announcement

        self.Announcement = Announcement
        self.champion = make_champion(username="champ")
        self.dojo = make_dojo("Ghent", champion=self.champion)
        self.url = reverse("dojo_updates", kwargs={"dojo_id": self.dojo.id})

    def _post(self, text):
        return self.client.post(self.url, {"text": text})

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_account_without_a_role_gets_404(self):
        self.client.force_login(make_mentor(username="outsider"))
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self._post("Hi").status_code, 404)

    def test_champion_sees_page_and_posts_an_update_dated_today(self):
        self.client.force_login(self.champion)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dojos/dojo_updates.html")

        response = self._post("  We've moved to the big room.  ")

        self.assertRedirects(response, self.url)
        update = self.Announcement.objects.get(dojo=self.dojo)
        self.assertEqual(update.text, "We've moved to the big room.")
        self.assertEqual(update.date, timezone.localdate())

    def test_mentor_can_post(self):
        mentor = make_mentor(username="mentor")
        add_member(self.dojo, mentor)
        self.client.force_login(mentor)
        self._post("Looking for a Python mentor.")
        self.assertTrue(self.Announcement.objects.filter(dojo=self.dojo).exists())

    def test_empty_or_too_long_text_is_rejected(self):
        self.client.force_login(self.champion)
        for text in ["   ", "x" * 501]:
            response = self._post(text)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertFalse(self.Announcement.objects.exists())

    def test_delete_only_within_own_dojo(self):
        own = self.Announcement.objects.create(dojo=self.dojo, date=date(2026, 1, 1), text="Mine")
        other_dojo = make_dojo("Antwerp", champion=make_champion(username="other"))
        other = self.Announcement.objects.create(dojo=other_dojo, date=date(2026, 1, 1), text="Theirs")
        self.client.force_login(self.champion)

        response = self.client.post(
            reverse("dojo_update_delete", kwargs={"dojo_id": self.dojo.id, "announcement_id": other.id})
        )
        self.assertEqual(response.status_code, 404)
        self.client.post(reverse("dojo_update_delete", kwargs={"dojo_id": self.dojo.id, "announcement_id": own.id}))

        self.assertEqual(list(self.Announcement.objects.values_list("text", flat=True)), ["Theirs"])

    def test_public_page_shows_the_five_newest(self):
        for day in range(1, 8):
            self.Announcement.objects.create(dojo=self.dojo, date=date(2026, 1, day), text=f"Update {day}")

        response = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": self.dojo.id}))

        self.assertContains(response, "From this dojo")
        self.assertEqual([a.text for a in response.context["announcements"]], [f"Update {d}" for d in range(7, 2, -1)])
        self.assertNotContains(response, "Update 2")

    def test_public_page_hides_the_section_without_updates(self):
        response = self.client.get(reverse("dojo_detail", kwargs={"dojo_id": self.dojo.id}))
        self.assertNotContains(response, "From this dojo")
