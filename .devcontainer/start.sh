#!/usr/bin/env bash
set -euo pipefail

# Trust our local dev CA inside the container (see .devcontainer/certs/README.md).
CA_SRC="/workspace/.devcontainer/certs/pki/ca.crt"
if [ -f "$CA_SRC" ]; then
    cp "$CA_SRC" /usr/local/share/ca-certificates/coolregistration-dev-ca.crt
    update-ca-certificates
else
    echo "warning: $CA_SRC not found - see .devcontainer/certs/README.md to generate it" >&2
fi

cd /workspace
python manage.py migrate

# Seed municipalities/boundaries/dojos from the bundled JSON dumps
# (geo/seed_data/, dojos/seed_data/dojos.json) rather than the real
# import_municipalities/import_boundaries/import_dojos commands, which need
# a local geopackage file and live network access (CoderDojo Belgium site +
# Nominatim geocoding) this container doesn't have. Both are no-ops once
# the data already exists, so this is safe to re-run.
python manage.py seed_geo
python manage.py seed_dojos
