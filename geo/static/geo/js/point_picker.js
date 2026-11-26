/* global ol */
"use strict";
/*
 * geo.widgets.PointPickerWidget: one pin on an OpenStreetMap map, for the
 * site's own forms. Click the map to put the pin there, drag it to move it,
 * or (with the keyboard) pan the map with the arrow keys and press "Put the
 * pin in the middle of the map". The hidden input gets the point as GeoJSON
 * in longitude/latitude, which Django's PointField reads. Its texts come
 * from the template's data attributes, its colours from the site's tokens.
 * Uses the OpenLayers build vendored next to the admin's map widget.
 */
(function () {
    function token(element, name, fallback) {
        const value = getComputedStyle(element).getPropertyValue(name).trim();
        return value || fallback;
    }

    function initPicker(root) {
        if (root.dataset.pointPickerReady) {
            return;
        }
        root.dataset.pointPickerReady = "1";
        const input = document.getElementById(root.dataset.pointPicker);
        const options = JSON.parse(
            document.getElementById(input.id + "_options").textContent,
        );
        const status = root.querySelector("[data-point-picker-status]");
        const actions = root.querySelector("[data-point-picker-actions]");
        const primary = token(root, "--primary", "#c94823");
        const ink = token(root, "--ink", "#1a1a1a");

        const pin = new ol.Feature();
        pin.setStyle(
            new ol.style.Style({
                image: new ol.style.Circle({
                    radius: 9,
                    fill: new ol.style.Fill({ color: primary }),
                    stroke: new ol.style.Stroke({ color: "#ffffff", width: 3 }),
                }),
            }),
        );
        const pins = new ol.Collection();
        const layers = [new ol.layer.Tile({ source: new ol.source.OSM() })];

        if (options.reference) {
            const reference = new ol.Feature(
                new ol.geom.Point(ol.proj.fromLonLat(options.reference)),
            );
            reference.setStyle(
                new ol.style.Style({
                    image: new ol.style.Circle({
                        radius: 7,
                        stroke: new ol.style.Stroke({ color: ink, width: 2 }),
                        fill: new ol.style.Fill({
                            color: "rgba(255, 255, 255, 0.6)",
                        }),
                    }),
                    text: root.dataset.textReference
                        ? new ol.style.Text({
                              text: root.dataset.textReference,
                              offsetY: -18,
                              font: "600 13px Nunito, sans-serif",
                              fill: new ol.style.Fill({ color: ink }),
                              stroke: new ol.style.Stroke({
                                  color: "#ffffff",
                                  width: 3,
                              }),
                          })
                        : undefined,
                }),
            );
            layers.push(
                new ol.layer.Vector({
                    source: new ol.source.Vector({ features: [reference] }),
                }),
            );
        }
        layers.push(
            new ol.layer.Vector({
                source: new ol.source.Vector({ features: pins }),
                updateWhileInteracting: true,
            }),
        );

        const mapElement = document.getElementById(input.id + "_map");
        const view = new ol.View({ zoom: options.default_zoom });
        const map = new ol.Map({
            target: mapElement,
            layers: layers,
            view: view,
            keyboardEventTarget: mapElement,
        });
        map.addInteraction(new ol.interaction.Translate({ features: pins }));

        function describe() {
            const geometry = pin.getGeometry();
            if (geometry && pins.getLength()) {
                const lonLat = ol.proj.toLonLat(geometry.getCoordinates());
                status.textContent = root.dataset.textPinned
                    .replace("{lat}", lonLat[1].toFixed(5))
                    .replace("{lon}", lonLat[0].toFixed(5));
            } else if (options.reference && root.dataset.textEmptyReference) {
                status.textContent = root.dataset.textEmptyReference;
            } else {
                status.textContent = root.dataset.textEmpty;
            }
        }

        function write() {
            const geometry = pin.getGeometry();
            if (geometry && pins.getLength()) {
                const lonLat = ol.proj.toLonLat(geometry.getCoordinates());
                input.value = JSON.stringify({
                    type: "Point",
                    coordinates: [
                        Number(lonLat[0].toFixed(6)),
                        Number(lonLat[1].toFixed(6)),
                    ],
                });
            } else {
                input.value = "";
            }
            describe();
        }

        function place(coordinate) {
            pin.setGeometry(new ol.geom.Point(coordinate));
            if (!pins.getLength()) {
                pins.push(pin);
            }
            write();
        }

        map.on("singleclick", (event) => place(event.coordinate));
        root.querySelector("[data-point-picker-centre]").addEventListener(
            "click",
            () => place(view.getCenter()),
        );
        root.querySelector("[data-point-picker-clear]").addEventListener(
            "click",
            () => {
                pins.clear();
                write();
            },
        );

        let start = null;
        if (input.value) {
            try {
                start = JSON.parse(input.value).coordinates;
            } catch (error) {
                start = null;
            }
        }
        if (start) {
            pins.push(pin);
            pin.setGeometry(new ol.geom.Point(ol.proj.fromLonLat(start)));
            view.setCenter(ol.proj.fromLonLat(start));
            view.setZoom(options.pin_zoom);
        } else if (options.reference) {
            view.setCenter(ol.proj.fromLonLat(options.reference));
            view.setZoom(options.pin_zoom - 2);
        } else {
            view.setCenter(
                ol.proj.fromLonLat([options.default_lon, options.default_lat]),
            );
        }
        // Only now: opening the page leaves the stored value as it is, so a
        // save without touching the map isn't a change.
        pin.on("change", write);
        actions.hidden = false;
        describe();
    }

    function initAll(scope) {
        scope.querySelectorAll("[data-point-picker]").forEach(initPicker);
    }

    document.addEventListener("DOMContentLoaded", () => initAll(document));
    document.addEventListener("htmx:afterSwap", (event) =>
        initAll(event.target),
    );
})();
