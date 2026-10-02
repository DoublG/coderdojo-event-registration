import re
import time
from unittest import mock

import requests
from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse
from django_redis import get_redis_connection

from . import geocoding
from .geocoding import find_province
from .models import AdministrativeBoundary, Municipality
from .widgets import BelgiumOSMWidget


class FindProvinceTests(TestCase):
    """geo.geocoding.find_province — factored out of the one-time
    map_dojo_provinces backfill so dojos.views.dojo_manage can keep
    Dojo.province in sync with Dojo.location whenever an owner edits their
    address (see geo.geocoding for the point-in-polygon/nearest-fallback
    logic itself)."""

    @classmethod
    def setUpTestData(cls):
        # Two adjacent 1x1-degree squares — real boundaries are far more
        # detailed, but the point-in-polygon logic doesn't care.
        cls.east_flanders = AdministrativeBoundary.objects.create(
            kind=AdministrativeBoundary.PROVINCE,
            name="East Flanders",
            boundary=MultiPolygon(Polygon(((3, 51), (3, 52), (4, 52), (4, 51), (3, 51)))),
        )
        cls.antwerp = AdministrativeBoundary.objects.create(
            kind=AdministrativeBoundary.PROVINCE,
            name="Antwerp",
            boundary=MultiPolygon(Polygon(((4, 51), (4, 52), (5, 52), (5, 51), (4, 51)))),
        )

    def test_point_inside_a_boundary(self):
        province = find_province(Point(3.5, 51.5, srid=4326))
        self.assertEqual(province, self.east_flanders)

    def test_point_just_outside_every_boundary_falls_back_to_nearest(self):
        province = find_province(Point(5.01, 51.5, srid=4326))
        self.assertEqual(province, self.antwerp)


class MapWidgetAssetsTests(TestCase):
    """The admin's map widget loads OpenLayers from our own static files
    (geo/static/geo/vendor/), never from a CDN."""

    def test_every_script_and_stylesheet_is_ours(self):
        urls = re.findall(r'(?:src|href)="([^"]+)"', str(BelgiumOSMWidget().media))
        self.assertIn(static("geo/vendor/ol-10.9.0/ol.js"), urls)
        self.assertIn(static("geo/vendor/ol-10.9.0/ol.css"), urls)
        for url in urls:
            self.assertTrue(url.startswith(settings.STATIC_URL), f"{url} is loaded from another site")
            self.assertIsNotNone(finders.find(url.removeprefix(settings.STATIC_URL)), f"{url} doesn't exist")

    def test_the_dojo_admin_page_loads_them(self):
        from accounts.models import User
        from dojos.testing import make_dojo

        dojo = make_dojo("Ghent")
        self.client.force_login(User.objects.create_superuser("root", "root@example.com", "pw"))
        response = self.client.get(reverse("admin:dojos_dojo_change", args=[dojo.id]))
        self.assertContains(response, static("geo/vendor/ol-10.9.0/ol.js"))
        self.assertNotContains(response, "cdn.jsdelivr.net")


class GeocodingTests(TestCase):
    """geo.geocoding.geocode: the cache, our own municipalities, and at most
    one Nominatim request a second for the whole site."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # the lookups, the Nominatim slot and back-off live there
        Municipality.objects.create(postal_code="9000", name="Gent", center=Point(3.72, 51.05, srid=4326))
        Municipality.objects.create(postal_code="9050", name="Gentbrugge", center=Point(3.76, 51.04, srid=4326))
        # One name, two places far apart: not something to answer locally.
        Municipality.objects.create(postal_code="3800", name="Melveren", center=Point(5.2, 50.8, srid=4326))
        Municipality.objects.create(postal_code="8000", name="Melveren", center=Point(3.2, 51.2, srid=4326))

    def _nominatim(self, results=(), status=200, headers=None):
        """A patched requests.get answering like Nominatim."""
        response = mock.Mock(status_code=status, headers=headers or {})
        response.json.return_value = [{"lat": str(lat), "lon": str(lon)} for lat, lon in results]
        if status >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(str(status))
        return mock.patch("geo.geocoding.requests.get", return_value=response)

    def test_the_same_search_written_differently_is_one_entry(self):
        self.assertEqual(geocoding.normalise(" Kerkstraat 1,  9000 GENT, Belgium "), "kerkstraat 1 9000 gent")
        with self._nominatim([(51.05, 3.72)]) as get:
            geocoding.geocode("Kerkstraat 1, 9000 Gent")
            self.assertEqual(geocoding.geocode("kerkstraat 1 9000 gent, België"), (51.05, 3.72))
        self.assertEqual(get.call_count, 1)

    def test_postcodes_and_town_names_come_from_our_own_municipalities(self):
        with self._nominatim() as get:
            self.assertEqual(geocoding.geocode("9000"), (51.05, 3.72))
            self.assertEqual(geocoding.geocode("gent"), (51.05, 3.72))
            self.assertEqual(geocoding.geocode("9000 Gent"), (51.05, 3.72))
            self.assertEqual(geocoding.geocode("Gentbrugge 9050"), (51.04, 3.76))
        get.assert_not_called()

    def test_a_name_found_in_places_far_apart_asks_nominatim(self):
        with self._nominatim([(50.8, 5.2)]) as get:
            self.assertEqual(geocoding.geocode("Melveren"), (50.8, 5.2))
        get.assert_called_once()

    def test_a_no_match_is_cached_and_an_error_is_not(self):
        with self._nominatim([]) as get:
            self.assertIsNone(geocoding.geocode("Nowhere street"))
            self.assertIsNone(geocoding.geocode("Nowhere street"))
        self.assertEqual(get.call_count, 1)
        with self._nominatim(status=500), self.assertRaises(requests.RequestException):
            geocoding.geocode("Somewhere street")
        self._free_slot()
        with self._nominatim([(50.5, 4.5)]):
            self.assertEqual(geocoding.geocode("Somewhere street"), (50.5, 4.5))

    def _free_slot(self):
        get_redis_connection("default").delete(geocoding.SLOT_KEY)

    def test_at_most_one_request_a_second(self):
        with self._nominatim([(50.5, 4.5)]) as get:
            geocoding.geocode("Street one")
            with self.assertRaises(geocoding.GeocodingUnavailable):
                geocoding.geocode("Street two", wait=0)
            self.assertEqual(get.call_count, 1)
            # A command waits for its turn.
            started = time.monotonic()
            geocoding.geocode("Street three", wait=None)
            self.assertGreaterEqual(time.monotonic() - started, 0.5)
        self.assertEqual(get.call_count, 2)

    def test_too_many_requests_stops_every_call_for_a_while(self):
        with self._nominatim(status=429, headers={"Retry-After": "120"}), self.assertRaises(requests.RequestException):
            geocoding.geocode("Street one")
        self.assertGreater(get_redis_connection("default").ttl(geocoding.BACKOFF_KEY), 100)
        self._free_slot()
        with self._nominatim([(50.5, 4.5)]) as get, self.assertRaises(geocoding.GeocodingUnavailable):
            geocoding.geocode("Street two")
        get.assert_not_called()

    def test_without_redis_nominatim_is_never_called(self):
        with (
            mock.patch("geo.geocoding.get_redis_connection", side_effect=ConnectionError("down")),
            self._nominatim([(50.5, 4.5)]) as get,
            self.assertRaises(geocoding.GeocodingUnavailable),
        ):
            geocoding.geocode("Street one")
        get.assert_not_called()

    def test_what_was_typed_is_not_stored_as_text(self):
        with self._nominatim([(50.5, 4.5)]):
            geocoding.geocode("Kerkstraat 1, 9000 Gent")
        keys = [key.decode() for key in get_redis_connection("default").keys("*geo:geocode:*")]
        self.assertEqual(len(keys), 1)
        self.assertNotIn("kerkstraat", keys[0])
