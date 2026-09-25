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
    python manage.py seed_organisation
    python manage.py seed_guardians
    python manage.py seed_applications
    python manage.py seed_ninja_history
    python manage.py seed_faqs
    python manage.py seed_testimonials
    python manage.py seed_announcements
else
    echo "Demo data already present (events exist) - skipping demo seed."
fi

# The seeded site in several languages (DATA_MODEL.md §19): dojo languages by
# region, and the Dutch and French versions of the seeded texts. Rerun-safe
# (only touches rows still on their English seed text), so it runs on every
# start and also fills in a database seeded before it existed.
python manage.py seed_content_languages

# Example email templates (en/nl/fr) and two draft campaigns. No dates, only
# creates what's missing, so it's safe to run on every start.
python manage.py seed_mailing

# The engagement snapshot is rebuilt nightly by Celery beat; build it now so
# attendance badges and engagement segments work right after a start.
python manage.py rebuild_engagement

# seed_credentials.csv: a description per login (what a tester can do with it:
# champion of which dojos, parent of which children, a child login that's a
# youth mentor, ...), worked out from the data. Also gives seeded logins missing
# from the file a new password (DEBUG only).
python manage.py describe_seed_accounts

# Background jobs: the same two Celery workers as production (DATA_MODEL.md
# §11, "Production: two Celery workers under systemd"). `periodic` runs beat
# embedded (-B, the only beat) plus the jobs beat triggers; `mailing` runs
# everything else on the default queue. Neither reloads on code changes:
# restart them after editing a task (see CLAUDE.md, "Background jobs").
celery -A website worker -n periodic@%h -Q periodic -c 1 -B \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler -l INFO > celery-periodic.log 2>&1 &
celery -A website worker -n mailing@%h -Q celery -c 1 -l INFO > celery-mailing.log 2>&1 &

# start server
python manage.py runserver 0.0.0.0:8000
