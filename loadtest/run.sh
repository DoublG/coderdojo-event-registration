#!/bin/bash
# One load test run (CAPACITY.md, "Load tests"): Locust, plus the site's own
# /metrics/ sampled every 2 seconds (MySQL connections, each process's memory,
# Redis), into $LOADTEST_OUT (default ./loadtest-out):
#
#   loadtest/run.sh NAME USERS SPAWN_RATE DURATION [MODE]
#
#   LOADTEST_HOST       the site, e.g. http://coolregistration.localhost:8001 or https://<production>
#   LOADTEST_DATA       loadtest/prepare.py's output (not needed for MODE=public)
#   METRICS_TOKEN       the site's METRICS_TOKEN (without it, no /metrics/ samples)
#   LOADTEST_CLOSE=1    a new connection per request, as behind a proxy
#   LOADTEST_LABEL      a caption for the charts; LOADTEST_WORKERS, LOADTEST_LIMIT for the record
#   LOCUST              the locust binary (default: locust)
#
# MODE: mixed (default), rush, or public (visitors only, no login, no writes:
# the only mode allowed against a site that isn't local).
set -euo pipefail
NAME=$1 USERS=$2 RATE=$3 DURATION=$4 MODE=${5:-mixed}
OUT=${LOADTEST_OUT:-loadtest-out}
HOST=${LOADTEST_HOST:?set LOADTEST_HOST}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"

python3 - "$OUT/$NAME.meta.json" <<EOF
import json, sys, time
json.dump({"name": "$NAME", "users": $USERS, "spawn_rate": $RATE, "duration": "$DURATION", "mode": "$MODE",
           "host": "$HOST", "close": bool("${LOADTEST_CLOSE:-}"), "label": "${LOADTEST_LABEL:-$NAME}",
           "workers": "${LOADTEST_WORKERS:-}", "limit": "${LOADTEST_LIMIT:-}", "started": time.time()},
          open(sys.argv[1], "w"), indent=1)
EOF

SAMPLER=""
if [ -n "${METRICS_TOKEN:-}" ]; then
    python3 "$HERE/sample_metrics.py" "$HOST/metrics/" "$OUT/$NAME.metrics.jsonl" &
    SAMPLER=$!
fi
LOADTEST_MODE=$MODE ${LOCUST:-locust} -f "$HERE/locustfile.py" --host "$HOST" --headless \
    -u "$USERS" -r "$RATE" -t "$DURATION" --csv "$OUT/$NAME" --only-summary > "$OUT/$NAME.txt" 2>&1 || true
[ -n "$SAMPLER" ] && kill "$SAMPLER"
grep -A3 "Aggregated" "$OUT/$NAME.txt" | head -1
