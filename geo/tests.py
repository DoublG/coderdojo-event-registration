from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import TestCase

from .geocoding import find_province
from .models import AdministrativeBoundary


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
            kind=AdministrativeBoundary.PROVINCE, name="East Flanders",
            boundary=MultiPolygon(Polygon(((3, 51), (3, 52), (4, 52), (4, 51), (3, 51)))),
        )
        cls.antwerp = AdministrativeBoundary.objects.create(
            kind=AdministrativeBoundary.PROVINCE, name="Antwerp",
            boundary=MultiPolygon(Polygon(((4, 51), (4, 52), (5, 52), (5, 51), (4, 51)))),
        )

    def test_point_inside_a_boundary(self):
        province = find_province(Point(3.5, 51.5, srid=4326))
        self.assertEqual(province, self.east_flanders)

    def test_point_just_outside_every_boundary_falls_back_to_nearest(self):
        province = find_province(Point(5.01, 51.5, srid=4326))
        self.assertEqual(province, self.antwerp)
