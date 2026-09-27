import re

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse

from .geocoding import find_province
from .models import AdministrativeBoundary
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
