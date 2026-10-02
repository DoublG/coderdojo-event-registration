#!/bin/bash
# The same load runs against one checkout of the code, for a before/after
# comparison (CAPACITY.md, "Caching"): run it once on a `git worktree` of the
# old commit and once on the new one, with the same PREFIX convention
# (before/after), then summarize both folders into one file.
#
#   loadtest/compare.sh CODE_DIR OUT_DIR PREFIX
#
#   LOCUST          the locust binary of loadtest/requirements.txt's venv
#   LOADTEST_DATA   loadtest/prepare.py's output, made before the first run
#   SEEDED_MAX_REGISTRATION
#                   the highest events_registration id seed_scale left: every
#                   run starts from those bookings (the runs book sessions)
#
# Runs: 300 users with 4 and with 2 web workers (mixed load), and a rush of
# 500 families, all behind the cap (gunicorn.conf.py) with a new connection
# per request. Each starts on an empty cache (Redis db 4) and the seeded
# bookings. Needs the scaled database of "Measuring again" (test_capacity).
set -uo pipefail
CODE=$1 OUT=$2 PREFIX=$3
HERE=$(cd "$(dirname "$0")" && pwd)
MANAGE="$HERE/../manage.py"
MARK=${SEEDED_MAX_REGISTRATION:?set SEEDED_MAX_REGISTRATION}
export DB_NAME=test_capacity DEBUG=false SILK=false SECURE_COOKIES=false EMAIL_HOST= \
       REDIS_CACHE_DB=4 REDIS_CHANNELS_DB=5 CELERY_BROKER_DB=6 MAILING_BOUNCE_IMAP_HOST= METRICS_TOKEN=loadtest
export LOADTEST_HOST=http://coolregistration.localhost:8001 LOADTEST_OUT=$OUT LOADTEST_CLOSE=1 LOADTEST_LIMIT=25
: "${LOADTEST_DATA:?set LOADTEST_DATA}"
mkdir -p "$OUT"
cd "$CODE"

reset() {
    # Back to the seeded bookings, an empty cache and empty counters.
    python "$MANAGE" shell -c "
from django.db import connection
from django_redis import get_redis_connection
with connection.cursor() as c:
    c.execute('DELETE FROM events_registration_pathways WHERE registration_id > %s', [$MARK])
    c.execute('DELETE FROM events_registration WHERE id > %s', [$MARK])
get_redis_connection('default').flushdb()
" > /dev/null 2>&1
}

start_web() {
    gunicorn -k uvicorn.workers.UvicornWorker main:app -b 127.0.0.1:8001 -w "$1" > "$OUT/gunicorn-$PREFIX-$1.log" 2>&1 &
    WEB=$!
    until curl -s -o /dev/null http://127.0.0.1:8001/health/ -H "Host: coolregistration.localhost"; do sleep 1; done
}

stop_web() {
    kill "$WEB"
    wait "$WEB" 2>/dev/null
}

celery -A website worker -n periodic-load@%h -Q periodic -c 1 -B --scheduler django_celery_beat.schedulers:DatabaseScheduler \
    --max-tasks-per-child 100 --max-memory-per-child 200000 -l WARNING > "$OUT/celery-periodic-$PREFIX.log" 2>&1 &
PERIODIC=$!
celery -A website worker -n mailing-load@%h -Q celery -c 1 --max-tasks-per-child 100 --max-memory-per-child 200000 \
    -l WARNING > "$OUT/celery-mailing-$PREFIX.log" 2>&1 &
MAILING=$!

run() {  # NAME WORKERS USERS SPAWN_RATE DURATION MODE LABEL
    reset
    start_web "$2"
    LOADTEST_WORKERS=$2 LOADTEST_LABEL="$7" "$HERE/run.sh" "$PREFIX-$1" "$3" "$4" "$5" "$6"
    stop_web
}

run W4-300 4 300 20 4m mixed "4 workers, 300 users ($PREFIX)"
run W2-300 2 300 20 4m mixed "2 workers, 300 users ($PREFIX)"
run rush-500 4 500 50 2m rush "Rush of 500 families, 4 workers ($PREFIX)"

kill "$PERIODIC" "$MAILING"
wait 2>/dev/null
reset
echo "done $PREFIX"
