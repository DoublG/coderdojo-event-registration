# Open technical questions for Level27

Level27 sponsors the hosting, so this page is deliberately **not** about capacity or budget (how
much memory, CPU or disk the account gets) — it's the concrete technical configuration we still
need from them, or need them to confirm, to run safely. Versions and what's already confirmed are
in [`MAINTENANCE.md`](MAINTENANCE.md); the reasoning behind each ask is in [`CAPACITY.md`](CAPACITY.md).

**Resolved** (kept here only until the next quarterly review confirms they're stable, then move the
line to `MAINTENANCE.md`'s security log):

- ~~MySQL client development headers (`libmysqlclient-dev`)~~ — present, confirmed 8 Oct 2026.
- ~~GDAL, GEOS and PROJ~~ — present (GDAL 3.4.1, GEOS 3.10.2, PROJ 22), confirmed 8 Oct 2026;
  `django.contrib.gis` and `geo.functions.DistanceSphere` work.
- ~~A running Redis~~ — running since before 8 Oct 2026 (version 8.10.1), see below for its settings.
- ~~The worker component "celery" with both Celery workers' commands~~ — present and running.

## Still open

1. **Redis's `maxmemory-policy` is `allkeys-lru`, not `volatile-lru`.** Confirmed 8 Oct 2026:
   `maxmemory` 512 MB, policy `allkeys-lru`. Our design (`CLAUDE.md`, "Caching"; `CAPACITY.md`,
   "Redis") assumes `volatile-lru`, so that only keys with a timeout (cache entries, session
   copies) are ever evicted, and the Celery broker's queued tasks and the `/metrics/` counters —
   which carry no timeout on purpose — are never touched even when Redis is full. Under
   `allkeys-lru` those untimed keys are evictable too. Usage is tiny today (2.3 MB of 512 MB), so
   there's no live incident, but **ask Level27 to switch the policy to `volatile-lru`** (matching
   the devcontainer) rather than relying on headroom alone.
2. **The proxy's maximum request body size.** Should be 12 MB, like the devcontainer's
   `client_max_body_size` (`CAPACITY.md`, "Disk: files and uploads"), so a file just over the
   site's own 10 MB limit gets the site's own message instead of a generic proxy error. A
   13 MB POST to the live site on 8 Oct 2026 got a 403 (Django's CSRF check, not a size error),
   which suggests the body reached the application rather than being rejected by the proxy at
   12 MB — inconclusive, since it never tested past the CSRF check. Ask Level27 directly rather
   than relying on another empirical probe against the live site.
3. **How the proxy connects to the app's socket:** a new connection per request, or a pool kept
   open (keep-alive)? This decides how to size any per-worker concurrency cap correctly
   (`CAPACITY.md`, "Capping requests per web worker": a kept-open pool needs a higher cap, since
   idle connections take a place too).
4. **Whether Redis and MySQL are dedicated to this account or shared** with other Level27
   customers on the same instance — affects how much their `maxmemory`/connection limits can be
   trusted to stay put.
5. **Whether Level27 rotates `~/logs/worker-<id>/`** (the Celery workers' own log files) or
   whether that's ours to manage.
6. **Who patches what.** Working assumption: the operating system, MySQL and Redis are Level27's
   to patch; Python (pyenv) and the Python packages are ours. Confirm this explicitly
   (`MAINTENANCE.md`, "Still to confirm").
7. **Whether the proxy always sets `X-Forwarded-Proto` itself**, and can be trusted to. This is
   the precondition for turning `SECURE_SSL_REDIRECT` on safely (`MAINTENANCE.md`'s security log,
   30 Sep 2026 entry): Django trusts that header to decide whether a request was already HTTPS
   (`SECURE_PROXY_SSL_HEADER`), so if it could ever be unset or forged before reaching Apache, an
   HTTPS redirect based on it could loop or be bypassed. `SECURE_HSTS_SECONDS` is already raised to
   3600 (1 hour, confirmed 8 Oct 2026) as the lower-risk first step; this confirmation gates the
   next two (`SECURE_SSL_REDIRECT=true`, then 1 day and 1 year of HSTS).

## For context, not a question: MySQL's connection limit is tighter than assumed

Confirmed 8 Oct 2026 from the app's own DB connection: `max_connections` = 350,
**`max_user_connections` = 32** (our app's own DB user — also visible in the Level27 panel's package
configuration as "Connecties: 32", so it's a fixed property of the hosting package, not a server-wide
setting they could casually raise — and Level27 has since confirmed it can't be raised at all, see below). `CAPACITY.md`'s per-worker concurrency cap (`gunicorn.conf.py`, 25
per worker) was sized against the devcontainer's default of 151 and explicitly flagged "possibly lower
on shared hosting" — it's much lower. The formula in `CAPACITY.md` ("Capping requests per web worker"),
*workers × (cap − 1) + 5 < max_user_connections*, puts the whole safe budget at one worker with the cap
lowered to about 26, not the 3-worker/25-cap setup production actually runs (confirmed 8 Oct 2026:
`gunicorn --workers 3`, the panel's "server: uvicorn" setting). This isn't something to ask Level27 — the
worker count and cap are our own settings in their panel, and 32 appears to be fixed by the package — but
it means the connection-exhaustion protection `CAPACITY.md` describes is active again (production briefly
ran daphne with no cap at all, 6–8 Oct 2026) yet still not correctly *sized*, against a real limit
noticeably tighter than the devcontainer's.

**No longer theoretical — measured 8 Oct 2026** (`CAPACITY.md`, "Rerun against Level27's real limits"):
the devcontainer was rebuilt to match production exactly (3 workers, `max_user_connections` 32) and the
load test rerun. The old cap of 25 was the worst setting tested: a rush produced real `500` errors (not
just graceful `503` refusals) and a quarter of the throughput of every other configuration. **Fixed 8 Oct
2026:** `gunicorn.conf.py`'s default changed from 25 to 8 and deployed; confirmed live by reading the
running master's own environment rather than trusted blind (`MAINTENANCE.md`, Security log — the
`--check` diagnostic for this was itself wrong until the same day). This is our own panel setting, not
Level27's.

**Answered 8 Oct 2026: the limits can't be raised.** Level27 confirmed that `max_user_connections` (32)
and the package's other limits are part of the current hosting package. So the site has to be engineered
to work efficiently within them — shorter requests, fewer queries per request, slow work in Celery — not
sized up past them (`CAPACITY.md`, "Conclusion: what production can actually support today").

## Memory limit of the Celery component (answered 8 Oct 2026)

The panel's *Inzichten* shows the worker component (`py10102`, *Optioneel component*) with a limit of
about 512 MB; its curve matches the Celery processes' PSS (about 350 MB at rest, 410 MB while sending a
campaign, about 380 MB during the nightly engagement rebuild, also at the stretch scale since it works in
batches).

**Answered by the account holder, from the dashboard:**

- **What happens at the limit is our choice:** each additional component can be set to *kill* or
  *throttle* when it runs out of memory. It was on throttle on 8 October (the stretch test: every process
  in the component slowed down, mail stalled for 19 minutes). Recommended: **kill**, so the component
  recovers by itself in seconds (`CAPACITY.md`, "Load: Celery workers and mail").
- **Why the *Object cache* tab shows the same curve:** Celery and Redis (the broker and the cache) are set
  up together and interconnected, so one curve covers both.

- **Set to kill (8 October 2026) and tested:** a rebuild forced over the limit was killed after 19
  seconds and the mailing worker was back 10 seconds later, mail dispatch never stopped (`CAPACITY.md`).
- **The limit itself (512 MiB) is fixed by the package:** the dashboard shows it but doesn't let it be
  changed.
