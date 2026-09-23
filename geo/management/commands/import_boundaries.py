import geopandas
import pandas as pd
import shapely
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand

from geo.models import AdministrativeBoundary

GEOPACKAGE_PATH = "/home/erik/territorialdivisions_4326.gpkg"
# The source geometries are 3D and highly detailed (down to individual
# building outlines along the border); these boundaries are only ever
# used as a decorative reference layer on the admin map, so flatten to
# 2D and simplify to keep them light to transfer and render in-browser.
SIMPLIFY_TOLERANCE_DEGREES = 0.002


def load_geometry(shapely_geometry):
    simplified = shapely.force_2d(shapely_geometry).simplify(
        SIMPLIFY_TOLERANCE_DEGREES, preserve_topology=True
    )
    geometry = GEOSGeometry(simplified.wkt, srid=4326)
    if geometry.geom_type == "Polygon":
        geometry = MultiPolygon(geometry, srid=4326)
    return geometry


class Command(BaseCommand):
    help = (
        "Import the Belgian country outline and province boundaries from Geo.be "
        "Territorial Divisions, for use as reference layers on the admin GIS map "
        "widget. Needs GEOPACKAGE_PATH on disk - for local dev/container seeding "
        "use `manage.py seed_geo` instead, which loads a bundled dump of this "
        "command's output."
    )

    def handle(self, *args, **options):
        AdministrativeBoundary.objects.all().delete()

        territory = geopandas.read_file(GEOPACKAGE_PATH, layer="belgianterritory")[["namedut", "namefre", "geometry"]]
        for row in territory.itertuples():
            AdministrativeBoundary.objects.create(
                kind=AdministrativeBoundary.COUNTRY,
                name=row.namefre if pd.notna(row.namefre) else row.namedut,
                boundary=load_geometry(row.geometry),
            )

        provinces = geopandas.read_file(GEOPACKAGE_PATH, layer="province")[["namedut", "namefre", "geometry"]]
        provinces = provinces[provinces["namedut"].notna() | provinces["namefre"].notna()]

        # Each province sits entirely within one of Belgium's language
        # regions (Dutch-speaking Flanders or French-speaking Wallonia;
        # Brussels-Capital isn't a province), so use the region a province's
        # centroid falls in to pick the name in the correct official
        # language, rather than defaulting to one language for all of them.
        regions = geopandas.read_file(GEOPACKAGE_PATH, layer="region")[["namedut", "geometry"]]
        centroids = provinces.copy()
        centroids["boundary"] = provinces.geometry
        centroids["geometry"] = provinces.geometry.centroid
        joined = geopandas.sjoin(
            centroids, regions, predicate="within", how="left", lsuffix="province", rsuffix="region"
        )

        for row in joined.itertuples():
            is_flemish = row.namedut_region == "Vlaams Gewest"
            if is_flemish and pd.notna(row.namedut_province):
                name = row.namedut_province
            elif pd.notna(row.namefre):
                name = row.namefre
            else:
                name = row.namedut_province
            AdministrativeBoundary.objects.create(
                kind=AdministrativeBoundary.PROVINCE,
                name=name,
                boundary=load_geometry(row.boundary),
            )

        self.stdout.write(self.style.SUCCESS(
            f"Imported {AdministrativeBoundary.objects.filter(kind=AdministrativeBoundary.COUNTRY).count()} country "
            f"and {AdministrativeBoundary.objects.filter(kind=AdministrativeBoundary.PROVINCE).count()} province boundaries."
        ))
