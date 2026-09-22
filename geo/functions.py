from django.contrib.gis.db.models.functions import GeoFunc
from django.db.models import FloatField


class DistanceSphere(GeoFunc):
    """Great-circle distance in meters between two geodetic (SRID 4326)
    points, computed by the database via MySQL's ST_Distance_Sphere.

    Django's own Distance() function returns a raw, inaccurate planar
    degree value on MySQL for geodetic fields (it only gets proper
    spherical/spheroidal distance substitution on PostGIS) — this fills
    that gap using the same GeoFunc extension point Django itself uses,
    so the actual math still runs in the database's GIS engine, not in
    Python.
    """

    function = "ST_Distance_Sphere"
    output_field = FloatField()
    geom_param_pos = (0, 1)
