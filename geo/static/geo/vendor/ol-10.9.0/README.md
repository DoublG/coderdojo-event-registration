# OpenLayers, served from our own static files

The map widget in the Django admin (`geo.widgets.BelgiumOSMWidget`, with
`geo/js/belgium_map_widget.js`) loads OpenLayers from here instead of a CDN
(one connection less, and no admin's IP address goes to a third party).
BSD 2-Clause (`LICENSE.md`).

| File | npm package | Path in the package |
|---|---|---|
| `ol.js` | `ol@10.9.0` | `dist/ol.js`, without its last line (`//# sourceMappingURL=ol.js.map`, a 4 MB file we don't ship) |
| `ol.css` | `ol@10.9.0` | `ol.css`, unchanged |

The version is in the folder name, so an upgrade gets new URLs and no browser
keeps using a cached old copy.

The map tiles themselves still come from OpenStreetMap's tile servers
(`ol.source.OSM`): those can't be copied into the site.

## Upgrading

1. Download `https://registry.npmjs.org/ol/-/ol-<version>.tgz` and check it
   against the registry's checksum, the same way as for htmx
   (`core/static/core/vendor/htmx/README.md`).
2. Copy `dist/ol.js` (dropping the `sourceMappingURL` line) and `ol.css` into
   a new `ol-<version>/` folder, delete the old one, and update the paths in
   `geo/widgets.py` (`BelgiumOSMWidget.Media`). `geo.tests` fails while they
   point at a missing file.
