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
                "geo/vendor/ol-10.9.0/ol.css",
                "gis/css/ol3.css",
            )
        }
        js = (
            "geo/vendor/ol-10.9.0/ol.js",
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


class PointPickerWidget(OSMWidget):
    """
    A map with one pin, for the site's own forms (not the Django admin):
    a session's place, picked on OpenStreetMap.

    It reuses what the admin's widget stands on: Django's GIS form field and
    widget base (the value goes back and forth as GeoJSON, which
    ``forms.PointField`` reads and checks), the vendored OpenLayers and the
    OpenStreetMap tiles the Content-Security-Policy already allows, and
    Belgium's default view. Its own are the template and the script
    (``geo/js/point_picker.js``): one point only, buttons to put the pin in
    the middle of the map or take it away (so it works with the keyboard,
    and the map pans with the arrow keys), and translated texts. It leaves
    out the admin widget's province overlay, about 230 KB of GeoJSON on
    every page, which the tiles' own borders make unnecessary.

    The value is kept in longitude/latitude (``map_srid`` 4326), so the
    hidden input holds plain GeoJSON. Without JavaScript the input keeps its
    value, so saving the form never loses the pin. ``reference`` (a Point,
    optional) is shown as a second, hollow marker, e.g. the dojo's own
    location, and is where the map opens when there's no pin yet; the form
    names it (``reference_label``, on the map) and says what counts without
    a pin (``reference_empty_text``), since geo knows nothing of dojos.
    """

    template_name = "geo/widgets/point_picker.html"
    map_srid = 4326
    geom_type = "POINT"
    use_fieldset = True
    default_lon = BelgiumOSMWidget.default_lon
    default_lat = BelgiumOSMWidget.default_lat
    default_zoom = BelgiumOSMWidget.default_zoom
    pin_zoom = 16

    class Media:
        extend = False
        css = {"all": ("geo/vendor/ol-10.9.0/ol.css",)}
        js = ("geo/vendor/ol-10.9.0/ol.js", "geo/js/point_picker.js")

    def __init__(self, attrs=None, reference=None, reference_label="", reference_empty_text=""):
        super().__init__(attrs=attrs)
        self.reference = reference
        self.reference_label = reference_label
        self.reference_empty_text = reference_empty_text

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_attrs = context["widget"]["attrs"]
        options = {
            "default_lon": widget_attrs["default_lon"],
            "default_lat": widget_attrs["default_lat"],
            "default_zoom": widget_attrs["default_zoom"],
            "pin_zoom": self.pin_zoom,
        }
        if self.reference is not None:
            options["reference"] = [self.reference.x, self.reference.y]
        context["options"] = options
        context["reference_label"] = self.reference_label
        context["reference_empty_text"] = self.reference_empty_text
        return context
