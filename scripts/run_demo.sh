#!/usr/bin/env bash
# Run loadtest/run.sh against the live demo domain, once scripts/loadtest_demo.sh
# switch has pointed it at a throwaway database (CAPACITY.md, "Load testing
# production"; scripts/loadtest_demo.sh's own header explains why this needs
# the database switched first).
#
# Usage:
#   scripts/loadtest_demo.sh switch              # first, point the live app at a test DB
#   scripts/run_demo.sh NAME USERS RATE DURATION [MODE]   # then, run a test
#   scripts/loadtest_demo.sh restore             # and put the real database back when done
#
# Settings (environment variables):
#   LOADTEST_DATA      the data file from loadtest/prepare.py, run against the
#                       SAME throwaway database (required)
#   LOADTEST_HOST       default: https://demo.coolestprojects.be
#   LOADTEST_PASSWORD   default: scale-test (seed_scale's password; set this
#                        to match however the throwaway database's accounts
#                        were actually seeded)
#   LOCUST              the locust binary (default: locust; point this at a
#                        venv's locust if it's not on PATH, e.g.
#                        LOCUST=.loadtest-venv/bin/locust)
#
# MODE defaults to "mixed" (see loadtest/locustfile.py for "rush"/"public").
# This script sets LOADTEST_CONFIRM_REMOTE_HOST to match LOADTEST_HOST
# automatically -- that confirmation is otherwise a one-time, explicit
# per-host opt-in on purpose (locustfile.py's own docstring), so don't
# default it to something else without rereading why.
#
# Example, from the devcontainer or your own machine, after `switch`:
#   LOADTEST_DATA=loadtest-data.json scripts/run_demo.sh demo-mixed-20 20 5 2m

set -euo pipefail

NAME="${1:?usage: $0 NAME USERS RATE DURATION [MODE]}"
USERS="${2:?usage: $0 NAME USERS RATE DURATION [MODE]}"
RATE="${3:?usage: $0 NAME USERS RATE DURATION [MODE]}"
DURATION="${4:?usage: $0 NAME USERS RATE DURATION [MODE]}"
MODE="${5:-mixed}"

: "${LOADTEST_DATA:?set LOADTEST_DATA to the file from loadtest/prepare.py, run against the same throwaway database}"

export LOADTEST_HOST="${LOADTEST_HOST:-https://demo.coolestprojects.be}"
export LOADTEST_MODE="$MODE"
export LOADTEST_PASSWORD="${LOADTEST_PASSWORD:-scale-test}"
export LOADTEST_CONFIRM_REMOTE_HOST="$(python3 -c "from urllib.parse import urlparse; print(urlparse('$LOADTEST_HOST').hostname)")"
export LOADTEST_LABEL="${LOADTEST_LABEL:-$LOADTEST_HOST, $USERS users, $MODE}"

echo "Target: $LOADTEST_HOST (confirmed via LOADTEST_CONFIRM_REMOTE_HOST=$LOADTEST_CONFIRM_REMOTE_HOST)"
echo "Make sure scripts/loadtest_demo.sh status shows it's pointed at the throwaway database first."
echo

HERE="$(cd "$(dirname "$0")/.." && pwd)"
exec "$HERE/loadtest/run.sh" "$NAME" "$USERS" "$RATE" "$DURATION" "$MODE"
