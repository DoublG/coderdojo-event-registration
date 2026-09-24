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

# Demo data (champions, mentors + the organisation team, pathways, events,
# parents/ninjas, applications, ninja history with badges and belts, FAQs,
# testimonials). Order matters: seed_mentors needs each dojo's champion,
# seed_events needs pathways and the dojo teams (event teams), seed_ninja_history
# needs ninjas (seed_guardians), teams and pathways, and seed_faqs needs events.
#
# Only on a fresh DB (no Event rows yet): the db-data volume survives a
# container rebuild, and seed_events/seed_ninja_history generate dates
# relative to *today*, so re-running them on a later day would keep piling
# extra events onto the existing demo data. Wipe the DB (`docker compose
# down -v`) or run the commands by hand to reseed.
# Logins for the seeded accounts land in seed_credentials.csv (gitignored).
if python manage.py shell -c "import sys; from events.models import Event; sys.exit(1 if Event.objects.exists() else 0)"; then
    python manage.py seed_champions
    python manage.py seed_mentors
    python manage.py seed_pathways
    python manage.py seed_events
    python manage.py seed_guardians
    python manage.py seed_applications
    python manage.py seed_ninja_history
    python manage.py seed_faqs
    python manage.py seed_testimonials
    python manage.py seed_announcements
else
    echo "Demo data already present (events exist) - skipping demo seed."
fi

# start server
python manage.py runserver 0.0.0.0:8000
