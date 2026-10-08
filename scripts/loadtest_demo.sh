#!/usr/bin/env bash
# Point the live demo app at a throwaway database for load testing, and back.
#
# Why this exists: loadtest/locustfile.py's `mixed`/`rush` modes log in and
# book real sessions, so they refuse any host that isn't local -- on a site
# with real family data, pointing them at the public domain would create
# fake bookings and send real mail. This script makes that safe on a site
# that's explicitly still a demo with no real users: it repoints the *real*
# app (web + both Celery workers) at a separate, disposable database for the
# test window, so demo.coolestprojects.be genuinely serves only test data
# while you run the load test against it, then puts the real database back.
#
# Usage:
#   scripts/loadtest_demo.sh switch    # point the live app at the test DB
#   scripts/loadtest_demo.sh status    # which database is live right now
#   scripts/loadtest_demo.sh restore   # put the real database back
#
# Settings (environment variables):
#   DEPLOY_REMOTE       ssh target (default: py10102@c40a7b15f.l27powered.eu,
#                        same as scripts/deploy.sh)
#   LOADTEST_DB_HOST, LOADTEST_DB_PORT, LOADTEST_DB_NAME, LOADTEST_DB_USER,
#   LOADTEST_DB_PASSWORD
#                        the throwaway database's connection details.
#                        Required for `switch`, never hardcoded here or
#                        committed anywhere -- a fresh database from the
#                        Level27 panel gives you all five. Keep them on
#                        the server, owner-only, one file per database:
#                        ~/loadtest-db-<host>-<db name>.env (and that
#                        database's seed_credentials.csv copied as
#                        seed_credentials-<host>-<db name>.csv), so
#                        switching databases never overwrites another's.
#
# What `switch` does, over SSH, on the server (never touches your machine):
#   1. Backs up ~/app/.env to ~/app/.env.backup-before-loadtest (refuses to
#      overwrite an existing backup -- run `restore` first if one's already
#      there, so you never lose the real values).
#   2. Edits only the DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD lines in
#      place (sed), leaving every other setting -- SECRET_KEY, mail, Redis,
#      everything -- untouched.
#   3. Reloads the live gunicorn (graceful HUP, same mechanism
#      scripts/deploy.sh uses for a code deploy) and warm-restarts both
#      Celery workers, so nothing is left reading the old database.
#   4. Verifies via /metrics/ (table row counts) that the live site is
#      actually serving the new database, not the old one.
#
# `restore` does the same in reverse: copies the backup over .env, reloads,
# restarts Celery, verifies, and removes the backup (so a stale backup can
# never be mistaken for "still switched" later).
#
# This never touches the database itself (migrating/seeding/dropping the
# throwaway database, and provisioning it in the first place, are separate,
# manual steps -- see CAPACITY.md, "Load testing production"). Run
# loadtest/run_demo.sh (or locust directly) against the live domain only
# after `switch` has confirmed the swap, and run `restore` as soon as you're
# done -- don't leave the live demo pointed at throwaway data longer than
# the test needs.

set -euo pipefail

REMOTE="${DEPLOY_REMOTE:-py10102@c40a7b15f.l27powered.eu}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE")

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

CMD="${1:-}"
case "$CMD" in
    switch|status|restore) ;;
    *) echo "usage: $0 {switch|status|restore}" >&2; exit 2 ;;
esac

step "Checking connection"
"${SSH[@]}" true 2>/dev/null || die "cannot ssh to $REMOTE (is your key loaded?)"

if [ "$CMD" = status ]; then
    "${SSH[@]}" bash -s <<'REMOTE'
set -euo pipefail
echo "~/app/.env currently points at: $(grep -E '^DB_NAME=' ~/app/.env | cut -d= -f2)"
if [ -f ~/app/.env.backup-before-loadtest ]; then
    echo "a backup exists (~/app/.env.backup-before-loadtest), from: $(grep -E '^DB_NAME=' ~/app/.env.backup-before-loadtest | cut -d= -f2)"
    echo "-> looks switched to a test database; run 'restore' when done testing"
else
    echo "no backup present -> looks like the real database (normal state)"
fi
REMOTE
    exit 0
fi

if [ "$CMD" = switch ]; then
    : "${LOADTEST_DB_HOST:?set LOADTEST_DB_HOST}" "${LOADTEST_DB_PORT:?set LOADTEST_DB_PORT}"
    : "${LOADTEST_DB_NAME:?set LOADTEST_DB_NAME}" "${LOADTEST_DB_USER:?set LOADTEST_DB_USER}"
    : "${LOADTEST_DB_PASSWORD:?set LOADTEST_DB_PASSWORD}"

    step "Backing up ~/app/.env (refusing to overwrite an existing backup)"
    "${SSH[@]}" bash -s <<'REMOTE'
set -euo pipefail
if [ -f ~/app/.env.backup-before-loadtest ]; then
    echo "a backup already exists - run 'restore' first, or remove it by hand if you're sure" >&2
    exit 1
fi
cp ~/app/.env ~/app/.env.backup-before-loadtest
echo "backed up"
REMOTE

    step "Pointing ~/app/.env at the test database"
    "${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
sed -i \
  -e 's/^DB_HOST=.*/DB_HOST=${LOADTEST_DB_HOST}/' \
  -e 's/^DB_PORT=.*/DB_PORT=${LOADTEST_DB_PORT}/' \
  -e 's/^DB_NAME=.*/DB_NAME=${LOADTEST_DB_NAME}/' \
  -e 's/^DB_USER=.*/DB_USER=${LOADTEST_DB_USER}/' \
  -e 's/^DB_PASSWORD=.*/DB_PASSWORD=${LOADTEST_DB_PASSWORD}/' \
  ~/app/.env
grep -E '^DB_(HOST|PORT|NAME|USER)=' ~/app/.env
REMOTE
fi

if [ "$CMD" = restore ]; then
    step "Restoring ~/app/.env from the backup"
    "${SSH[@]}" bash -s <<'REMOTE'
set -euo pipefail
[ -f ~/app/.env.backup-before-loadtest ] || { echo "no ~/app/.env.backup-before-loadtest found - nothing to restore" >&2; exit 1; }
cp ~/app/.env.backup-before-loadtest ~/app/.env
rm -f ~/app/.env.backup-before-loadtest
grep -E '^DB_(HOST|PORT|NAME|USER)=' ~/app/.env
echo "restored and backup removed"
REMOTE
fi

step "Reloading gunicorn"
"${SSH[@]}" bash -s <<'REMOTE'
set -euo pipefail
MASTER="$(pgrep -u "$USER" -o -f "gunicorn.*py10102.socket" || true)"
[ -n "$MASTER" ] || { echo "no gunicorn master found on py10102.socket" >&2; exit 1; }
kill -HUP "$MASTER"
sleep 5
kill -0 "$MASTER" || { echo "gunicorn master died after reload" >&2; exit 1; }
echo "gunicorn $MASTER reloaded"
REMOTE

step "Restarting Celery workers (warm shutdown, Level27 starts them again)"
"${SSH[@]}" bash -s <<'REMOTE'
set -euo pipefail
celery_mains() {
    local pid parent
    for pid in $(pgrep -u "$USER" -f "celery -A website worker" || true); do
        parent="$(ps -o ppid= -p "$pid" | tr -d ' ')"
        tr '\0' ' ' < "/proc/$parent/cmdline" 2>/dev/null | grep -q "celery -A website worker" || echo "$pid"
    done
}
OLD="$(celery_mains | tr '\n' ' ')"
[ -n "$OLD" ] || { echo "no Celery workers found" >&2; exit 1; }
kill -TERM $OLD
for _ in $(seq 1 60); do
    alive=""
    for pid in $OLD; do kill -0 "$pid" 2>/dev/null && alive="$alive $pid"; done
    [ -z "$alive" ] && break
    sleep 1
done
[ -z "${alive:-}" ] || { echo "worker(s)$alive didn't stop in time" >&2; exit 1; }
cd ~/app
for _ in $(seq 1 18); do
    n="$("$HOME/.pyenv/versions/py10102-3.14.7/bin/python" -m celery -A website inspect ping --timeout 10 2>/dev/null | grep -c ': OK' || true)"
    [ "$n" -ge 2 ] && { echo "both workers answer"; exit 0; }
    sleep 5
done
echo "workers didn't come back within 90s - check ~/logs/worker-*/" >&2
exit 1
REMOTE

step "Verifying what's actually live"
"${SSH[@]}" bash -s <<'REMOTE'
set -euo pipefail
TOKEN="$(grep -E '^METRICS_TOKEN=' ~/app/.env | cut -d= -f2)"
HOST="$(grep -E '^ALLOWED_HOSTS=' ~/app/.env | cut -d= -f2 | cut -d, -f1)"
curl -s -o /dev/null -w 'GET / -> %{http_code}\n' --unix-socket /var/run/socket/py10102.socket -H "Host: $HOST" http://localhost/
curl -s --unix-socket /var/run/socket/py10102.socket -H "Host: $HOST" -H "Authorization: Bearer $TOKEN" \
  http://localhost/metrics/ | grep -E 'dojos_dojo"' || echo "(couldn't read table counts - check METRICS_TOKEN)"
echo "now pointing at: $(grep -E '^DB_NAME=' ~/app/.env | cut -d= -f2)"
REMOTE

step "Done ($CMD)"
