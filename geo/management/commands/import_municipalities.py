import geopandas
import pandas as pd
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from geo.models import Municipality

GEOPACKAGE_PATH = "/home/erik/territorialdivisions_4326.gpkg"


class Command(BaseCommand):
    help = (
        "Import Belgian municipal sections and postal districts "
        "from Geo.be Territorial Divisions."
    )

    def handle(self, *args, **options):
        municipalsectioncenter = geopandas.read_file(GEOPACKAGE_PATH, layer="municipalsectioncenter")[['namedut', 'namefre', 'geometry']]
        postaldistrict = geopandas.read_file(GEOPACKAGE_PATH, layer="postaldistrict")[['postcode', 'geometry']]
        frame = municipalsectioncenter.sjoin(postaldistrict)

        Municipality.objects.all().delete()

        for l in frame.itertuples():
            p = l.geometry
            municipality = Municipality(
                postal_code=int(l.postcode),
                name=l.namefre if pd.notna(l.namefre) else l.namedut,
                center=Point(
                    p.x,
                    p.y,
                    srid=4326,
                ),
            )
            municipality.save()
