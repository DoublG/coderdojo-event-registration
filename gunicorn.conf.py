# gunicorn reads this file by itself from the directory it starts in (~/app on
# Level27, /workspace in the devcontainer), so it applies to the command
# Level27 manages: gunicorn -k uvicorn.workers.UvicornWorker main:app.
#
# Caps what each web worker takes on at once (uvicorn's limit_concurrency):
# beyond it uvicorn answers 503 at once instead of starting the request.
# Every request in progress holds its own MySQL connection (Django runs each
# one in a thread of its own), so this also caps the site's connections at
# workers x limit (+ about 5 for Celery), under MySQL's max_connections.
# uvicorn counts open connections, so an open notification WebSocket takes a
# place too. Measured in CAPACITY.md, "Capping requests per web worker": 25
# was only ever validated against the devcontainer's 151-connection MySQL
# default. Rerun on 8 Oct 2026 against production's real numbers (3 workers,
# `max_user_connections` 32), 25 produced real 500 errors under a rush (not
# just 503 refusals) and a quarter of the throughput of every other setting
# tested; 8 eliminated every 500 in both a rush and normal heavy load.
import os

from uvicorn.workers import UvicornWorker

UvicornWorker.CONFIG_KWARGS = {
    **UvicornWorker.CONFIG_KWARGS,
    "limit_concurrency": int(os.environ.get("UVICORN_LIMIT_CONCURRENCY", "8")),
}
