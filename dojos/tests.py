from unittest.mock import patch

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import DojoOwner
from geo.models import AdministrativeBoundary
from notifications.consumers import NotificationConsumer
from notifications.services import notify

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
        Mentor.objects.create(name="Some Volunteer", dojo=dojo, role=Mentor.VOLUNTEER)
        Mentor.objects.create(name="Lead", dojo=dojo, role=Mentor.LEAD_COACH, owner_account=owner)

        response = self.client.get(reverse("dojo_team", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.status_code, 200)
        mentors = list(response.context["mentors"])
        self.assertEqual(mentors[0].role, Mentor.LEAD_COACH)


class DojoDashboardViewTests(TestCase):
    def test_dojo_with_no_sessions_still_renders(self):
        owner = DojoOwner.objects.create(username="owner1")
        dojo = Dojo.objects.create(name="Ghent", owner=owner)
        self.client.force_login(owner)

        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["session"])

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
