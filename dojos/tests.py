from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.urls import reverse

from accounts.models import DojoOwner

from .models import Dojo, Mentor


class DojoListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Dojo.objects.create(name="Ghent", location=Point(3.7174, 51.0543, srid=4326))
        Dojo.objects.create(name="Antwerp", location=Point(4.4025, 51.2194, srid=4326))

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
        dojo = Dojo.objects.create(name="Ghent")
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id}))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["session"])

    def test_missing_dojo_is_404(self):
        response = self.client.get(reverse("dojo_dashboard", kwargs={"dojo_id": 999999}))
        self.assertEqual(response.status_code, 404)


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
