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

# Demo data (owners, mentors, pathways, events, guardians/children, history,
# FAQs, testimonials). Order matters: seed_mentors needs dojo owners (Lead
# Coach = the owner's login), seed_participant_history needs participants
# (seed_guardians), mentors and pathways, and seed_faqs needs events.
#
# Only on a fresh DB (no Event rows yet): the db-data volume survives a
# container rebuild, and seed_events/seed_participant_history generate dates
# relative to *today*, so re-running them on a later day would keep piling
# extra events onto the existing demo data. Wipe the DB (`docker compose
# down -v`) or run the commands by hand to reseed.
# Logins for the seeded accounts land in seed_credentials.csv (gitignored).
if python manage.py shell -c "import sys; from events.models import Event; sys.exit(1 if Event.objects.exists() else 0)"; then
    python manage.py seed_dojo_owners
    python manage.py seed_mentors
    python manage.py seed_pathways
    python manage.py seed_events
    python manage.py seed_guardians
    python manage.py seed_applications
    python manage.py seed_participant_history
    python manage.py seed_faqs
    python manage.py seed_testimonials
else
    echo "Demo data already present (events exist) - skipping demo seed."
fi
