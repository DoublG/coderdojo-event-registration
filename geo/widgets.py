import json

from django.contrib.gis.admin import GISModelAdmin
from django.contrib.gis.forms.widgets import OSMWidget


class BelgiumOSMWidget(OSMWidget):
    """
    OSM-based admin map widget centered on Belgium, with the country
    outline and province boundaries drawn as a reference overlay so
    editors can see roughly where they're placing a point.
    """

    # Center/zoom picked to fit all of Belgium (lon 2.54-6.41, lat 49.50-51.51
    # per the Geo.be territorial divisions dataset used in import_boundaries).
    default_lon = 4.475
    default_lat = 50.505
    default_zoom = 8

    class Media:
        # extend=False: replace OSMWidget's Media (which pulls in the stock
        # gis/js/OLMapWidget.js) rather than merging with it, since our JS
        # below is a full fork of that file and both loading together would
        # redeclare the same JS classes.
        extend = False
        css = {
            "all": (
                "https://cdn.jsdelivr.net/npm/ol@v10.9.0/ol.css",
                "gis/css/ol3.css",
            )
        }
        js = (
            "https://cdn.jsdelivr.net/npm/ol@v10.9.0/dist/ol.js",
            "geo/js/belgium_map_widget.js",
        )

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs)
        self.attrs["boundaries_geojson"] = self._boundaries_geojson()

    @staticmethod
    def _boundaries_geojson():
        from geo.models import AdministrativeBoundary

        features = [
            {
                "type": "Feature",
                "properties": {"kind": boundary.kind, "name": boundary.name},
                "geometry": json.loads(boundary.boundary.geojson),
            }
            for boundary in AdministrativeBoundary.objects.all()
        ]
        return json.dumps({"type": "FeatureCollection", "features": features})


class BelgiumGISModelAdmin(GISModelAdmin):
    gis_widget = BelgiumOSMWidget
