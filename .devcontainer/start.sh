#!/usr/bin/env bash
set -euo pipefail

# Local dev TLS for coolregistration.localhost (see .devcontainer/certs/README.md,
# the same commands). Git keeps none of it, so a fresh checkout has to make it.
# The CA is only made when missing: your host trusts it, and a new one would
# need trusting again. The server certificate is made again when it's missing,
# expires within 30 days, or wasn't issued by the current CA. The proxy
# container keeps restarting until the files exist (restart: unless-stopped),
# then serves them.
ensure_dev_certs() {
    local certs=/workspace/.devcontainer/certs
    local pki="$certs/pki"
    local host=coolregistration.localhost
    local crt="$pki/issued/$host.crt"
    local key="$pki/private/$host.key"

    mkdir -p "$pki/private" "$pki/issued"

    if [ ! -f "$pki/ca.crt" ] || [ ! -f "$pki/private/ca.key" ]; then
        echo "Creating the local dev CA ($pki/ca.crt) - trust it on your host, see $certs/README.md"
        openssl genrsa -out "$pki/private/ca.key" 4096
        openssl req -x509 -new -nodes -key "$pki/private/ca.key" -sha256 -days 3650 \
            -subj "/CN=$host Dev CA/O=CoderDojo Belgium Dev" \
            -out "$pki/ca.crt"
        rm -f "$crt"
    fi

    if [ -f "$crt" ] && [ -f "$key" ] && [ -f "$certs/fullchain.pem" ] && [ -f "$certs/server.key" ] \
        && openssl x509 -in "$crt" -noout -checkend $((30 * 24 * 3600)) > /dev/null \
        && openssl verify -CAfile "$pki/ca.crt" "$crt" > /dev/null 2>&1; then
        return
    fi

    echo "Creating the TLS certificate for $host"
    cat > "$pki/server-ext.cnf" <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = $host

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = $host
EOF
    openssl genrsa -out "$key" 2048
    openssl req -new -key "$key" -out "$pki/$host.csr" -config "$pki/server-ext.cnf"
    openssl x509 -req -in "$pki/$host.csr" -CA "$pki/ca.crt" -CAkey "$pki/private/ca.key" \
        -CAcreateserial -out "$crt" -days 825 -sha256 \
        -extfile "$pki/server-ext.cnf" -extensions v3_req
    rm -f "$pki/$host.csr"
    cat "$crt" "$pki/ca.crt" > "$certs/fullchain.pem"
    cp "$key" "$certs/server.key"
    chmod 600 "$certs/server.key" "$key" "$pki/private/ca.key"

    # Hand the files to whoever owns the checkout, so the host can read ca.crt
    # (to trust it) and delete them to start over.
    chown -R --reference="$certs" "$pki" "$certs/fullchain.pem" "$certs/server.key"
}
ensure_dev_certs

# Trust our local dev CA inside the container (see .devcontainer/certs/README.md).
CA_SRC="/workspace/.devcontainer/certs/pki/ca.crt"
if [ -f "$CA_SRC" ]; then
    cp "$CA_SRC" /usr/local/share/ca-certificates/coolregistration-dev-ca.crt
    update-ca-certificates
else
    echo "warning: $CA_SRC not found - see .devcontainer/certs/README.md to generate it" >&2
fi

cd /workspace

# STATICFILES_DIRS (website/settings.py) lists the project-level static/ folder
# for files that belong to no app. Git doesn't keep empty folders, so on a
# fresh checkout it's missing and every manage.py command warns
# (staticfiles.W004). The app's own files are in each app's static/ folder.
mkdir -p static

# DEBUG=false (docker-compose.yml) runs the site like production, to check its
# speed. The same test for "on" as django-environ's (website/settings.py).
case "${DEBUG:-}" in
    [Tt][Rr][Uu][Ee]|[Oo][Nn]|[Oo][Kk]|[Yy]|[Yy][Ee][Ss]|1) debug=1 ;;
    *) debug=0 ;;
esac

# nginx serves /static/ from staticfiles/ when a file is there, else asks
# Django (nginx.conf). With DEBUG off Django serves no static files, so they're
# collected there; with DEBUG on it's emptied, or nginx would keep serving an
# old copy of a file you're editing. The folder itself stays: nginx's bind
# mount is pinned to it.
mkdir -p staticfiles
if [ "$debug" = 1 ]; then
    find staticfiles -mindepth 1 -delete
else
    python manage.py collectstatic --noinput --clear --verbosity 0
fi

# The help centre (docs/, Sphinx) in en/fr/nl, served by nginx at /docs/.
# Incremental, so only changed pages are rebuilt. It writes into docs/build/
# without deleting it, which keeps the proxy's bind mount on it working (see
# docs/README.md). A broken docs page never stops the site from starting.
make -C docs html-all -s || echo "warning: the docs build failed - see the output above" >&2

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
    # Children signed up at several dojos, and three sessions filled to test
    # the waiting list (full with children waiting, exactly full, one place left).
    python manage.py seed_upcoming_registrations
    python manage.py seed_faqs
    python manage.py seed_testimonials
    python manage.py seed_announcements
    python manage.py seed_sponsors
    # A few seeded accounts with two-step login on (key in seed_credentials.csv's
    # totp_secret column). Only here, so a restart never turns it back on for
    # an account a tester turned it off for.
    python manage.py seed_two_step
    # A seeded parent and mentor that log in with an emailed link (DATA_MODEL.md
    # §24); the links arrive in Mailpit. Fresh databases only, like the above.
    python manage.py seed_login_links
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

# The testers' authenticator (2FAuth at /otp/, the `otp` service): the current
# code of every account with two-step login, filled from the data. Run it again
# after someone's app changes. A vault that's down never stops the site starting.
python manage.py seed_otp_vault || echo "seed_otp_vault failed: the testers' authenticator at /otp/ isn't filled."

# Background jobs: the same two Celery workers as production (DATA_MODEL.md
# §11, "Production: two Celery workers under systemd"). `periodic` runs beat
# embedded (-B, the only beat) plus the jobs beat triggers; `mailing` runs
# everything else on the default queue. Neither reloads on code changes:
# restart them after editing a task (see CLAUDE.md, "Background jobs").
celery -A website worker -n periodic@%h -Q periodic -c 1 -B \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler -l INFO > celery-periodic.log 2>&1 &
celery -A website worker -n mailing@%h -Q celery -c 1 -l INFO > celery-mailing.log 2>&1 &

# Where to go: everything is behind nginx on 443 (docker-compose.yml publishes
# no other port), so these, not VS Code's localhost:<port>, are the addresses.
# *.localhost resolves to this machine by itself; no hosts-file entry needed.
cat <<'EOF'

  CoderDojo dev environment (the site answers once the server below has started):
    Site               https://coolregistration.localhost/
    Mail (Mailpit)     https://coolregistration.localhost/mails/
    phpMyAdmin         https://coolregistration.localhost/phpmyadmin/
    Login codes (2FA)  https://coolregistration.localhost/otp/
    Help docs          https://coolregistration.localhost/docs/
    Seeded logins      seed_credentials.csv

EOF

# start server: runserver while developing (reloads on every change, serves the
# static files); with DEBUG off the command production runs (gunicorn with
# uvicorn workers, main.py), so what you measure is how the site behaves there.
# More workers: WEB_CONCURRENCY=<n> (gunicorn reads it itself; default 1).
if [ "$debug" = 1 ]; then
    python manage.py runserver 0.0.0.0:8000
else
    gunicorn -k uvicorn.workers.UvicornWorker main:app -b 0.0.0.0:8000 --access-logfile -
fi
