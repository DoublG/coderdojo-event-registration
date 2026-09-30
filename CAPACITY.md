# Capacity: database growth, load and memory

How big the database gets, how much load each component takes, and how much memory Django, the Celery
workers and Redis need. For developers and whoever runs the platform. Measured on **30 September 2026**
in the devcontainer; rerun the measurements (see [Measuring again](#measuring-again)) after a large change
and at least once a year. Versions and updates are in [`MAINTENANCE.md`](MAINTENANCE.md); the design of
the workers is in [`DATA_MODEL.md`](DATA_MODEL.md) §11.

**In short:**

- **The database grows by about 350 MB a year** at 100 dojos and 6,000 families (1.6 GB after five
  years). Two thirds of that is the mail log: each mail keeps its full text. Clearing mail text after
  12 months, as the privacy register already promises, saves about a quarter of it.
- **The whole application needs about 1.5 GB of memory at its peak** with 4 web workers: 750 MB web,
  650 MB Celery (during the nightly rebuild) and under 50 MB Redis. Plan **2 GB** for the account.
- **Two problems showed up under load and need fixing before a busy registration opening:**
  1. Signing up at the same moment **overbooks sessions** (25 confirmed places on a session of 22).
  2. **Every request in progress holds its own database connection**, so a rush uses up MySQL's
     connection limit and the site answers with errors.

---

## Contents

1. [How it was measured](#how-it-was-measured)
2. [Database growth](#database-growth)
3. [Memory per component](#memory-per-component)
4. [Load: web requests](#load-web-requests)
5. [Load: Celery workers and mail](#load-celery-workers-and-mail)
6. [Redis](#redis)
7. [Findings and what to do](#findings-and-what-to-do)
8. [Watching production](#watching-production)
9. [Questions for Level27](#questions-for-level27)
10. [Measuring again](#measuring-again)

---

## How it was measured

- **A database at scale.** `manage.py seed_scale --scenario growth` filled a separate database
  (`test_capacity`) with one year of the *growth* scenario below: 100 dojos with their teams, 7,800
  guardian accounts, 9,000 children, 1,400 sessions, 29,400 bookings, 189,000 mails rendered from the real
  templates, 115,000 audit log entries, consents, badges, belts and the engagement snapshot. It took 53
  seconds and peaked at 409 MB.
- **Bytes per row** come from that database (`capacity_report --measure`, stored in
  `monitoring/row_sizes.json`); **rows per year** come from how the site works: which actions write which
  rows (`monitoring/capacity.py`, `GROWTH`).
- **A production-like run** on that database: `DEBUG` and django-silk off, gunicorn with uvicorn workers
  (production's command) and the two Celery workers with production's options, all with their own
  Redis databases, so the dev site wasn't touched.
- **Load** from [Locust](https://locust.io) (`loadtest/locustfile.py`): visitors, families that log in and
  book, and dojo teams taking attendance, plus a registration rush.
- **Memory** is **PSS** (proportional set size), read from `/proc/<pid>/smaps_rollup` every few seconds.
  RSS counts the memory that forked processes share once per process, so adding up RSS overstates the
  total by a lot (a Celery worker's parent and child both show about 205 and 145 MB RSS, but share most
  of it).
- **Limits of the test:** the devcontainer has 20 cores and plenty of memory, and the load generator runs
  on the same machine. Response times on Level27 will differ; the memory figures and the ratios between
  runs carry over.

## Database growth

Three scenarios, a year's volumes each (`monitoring/capacity.py`, `SCENARIOS`; change them when real
figures are known):

| Scenario | Dojos | Families | Sessions | Bookings | Mails |
|---|---:|---:|---:|---:|---:|
| `today` | 60 | 3,000 | 600 | 9,000 | 86,000 |
| `growth` | 100 | 6,000 | 1,200 | 24,000 | 189,000 |
| `stretch` | 150 | 12,000 | 3,000 | 75,000 | 451,000 |

Mail per family per year: confirmations and reminders per booking to each guardian (about 1.3 per
child), plus 6 new-sessions digests, 6 organisation campaigns, 6 dojo mailings, a journey and account mail.

**Projected size** (data plus indexes, on top of today's 11 MB):

| Scenario | After 1 year | After 3 years | After 5 years | 5 years, mail text cleared after 12 months |
|---|---:|---:|---:|---:|
| `today` | 165 MB | 467 MB | 768 MB | 585 MB |
| `growth` | 350 MB | 1.0 GB | 1.64 GB | 1.25 GB |
| `stretch` | 829 MB | 2.38 GB | 3.95 GB | 3.02 GB |

**Where it goes** (growth scenario, after 5 years): mail log 1.15 GB (70%), audit log 289 MB (18%),
engagement changes 52 MB, bookings with their pathways 54 MB, badges 24 MB, consents 13 MB; everything
else is small. **Measured bytes per row:**

| Table | Bytes per row | What makes a row |
|---|---:|---|
| `mailing_emailmessage` | 1,303 | every mail: its subject and body (557 bytes with the current templates), address, keys, 6 indexes |
| `django_session` | 981 | a login session (bounded: expired ones are removed daily) |
| `auditlog_logentry` | 525 | every recorded change (a booking, an attendance mark, a new account, ...) |
| `accounts_user` | 519 | an account |
| `events_ninjabadge` | 366 | an awarded badge |
| `events_ninjaengagement` | 281 | a child's snapshot at a dojo (rebuilt nightly, bounded) |
| `events_event` | 281 | a session (more with long descriptions and translations) |
| `accounts_ninja` | 242 | a child |
| `events_registration` | 232 | a booking |
| `mailing_consentevent` | 191 | a consent change |
| the many-to-many links | 140–165 | a session's team and pathways, a booking's pathways |

Worth knowing:

- **Mail text is the lever.** The growth scenario's 36,000 campaign mails a year, at 3 KB of text instead
  of the seeded templates' 0.5 KB, add about 90 MB a year. The privacy register's `mail_content` rule ("subject, body and address cleared
  after 12 months") isn't applied by the retention job yet; building it is the single biggest saving.
  InnoDB only gives the space back to the disk after `OPTIMIZE TABLE` on that table (it reuses it
  for new rows either way).
- **Nothing is deleted when accounts age out:** accounts, children and bookings are anonymised, not
  removed, so those tables only grow. The audit log is the exception: an erased account's entries go.
- **Outside the database's own size:** MySQL's binary logs (by default 30 days of every change: tens of MB
  at this write rate, more while a campaign is queued), backups (a copy per retained backup), and `media/` (uploaded photos and
  banners; standard images are shared, not copied, see CLAUDE.md "Standard images").

## Memory per component

PSS in MB, production-like (`DEBUG` off). *Idle* is after start-up and a few requests; *peak* is the
highest seen in any test.

| Component | Processes | Idle | Peak | Peak when |
|---|---|---:|---:|---|
| gunicorn master | 1 | 18 | 18 | |
| Web worker (uvicorn) | 1 per `WEB_CONCURRENCY` | 110–135 each | 180–290 each | 300 users; each worker grows while it serves several requests at once |
| — 2 web workers, total | 3 | 265 | 650 | registration rush, 500 users |
| — 4 web workers, total | 5 | 460 | 750 | 300 users |
| Celery `periodic` (parent, pool child, beat) | 3 | 255 | 255 | its jobs are short |
| Celery `mailing` (parent, pool child) | 2 | 160 | 385 | nightly engagement rebuild (child at 300 MB RSS, then replaced) |
| Redis (all three uses) | 1 | 3 | 5 | load tests on top of the dev data |
| Open notification WebSockets | | | +15 for 400 | about 40 KB each |

**Budget:** 750 MB web (4 workers) + 650 MB Celery + 50 MB Redis ≈ **1.45 GB at peak**, 0.9 GB idle.
Plan **2 GB** for the account. With 2 web workers: about 1.3 GB at peak, but see the load results below.
MySQL isn't in this budget: on Level27 it runs separately (to confirm, see
[Questions for Level27](#questions-for-level27)).

**Celery's per-child limit.** Both workers recycle their child at `--max-memory-per-child 200000`
(200 MB, compared with the child's peak RSS after each task). An idle child sits at 143–148 MB RSS, so
there are about 50 MB of room. The nightly engagement rebuild takes the mailing child to 300 MB (4.9
seconds for 9,000 children), after which Celery replaces it, as intended: the memory goes back. A
campaign launch stays at 160 MB (the audience is queued in chunks). The periodic worker's child never came
near the limit. The limit is right as it is; watch for "exceeded memory limit" in the worker log after
every task, which would mean the baseline has grown.

## Load: web requests

A mixed load: 6 visitors to 3 families to 1 dojo team member, each waiting 2 to 8 seconds between
clicks. Times in milliseconds.

| Run | Web workers | Users | Requests/s | Median | p95 | p99 | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 2 | 100 | 21.6 | 42 | 110 | 230 | 0 |
| B | 2 | 300 | 62.3 | 92 | 610 | 1,700 | 14 (0.1%) |
| D | 4 | 300 | 64.5 | 33 | 110 | 260 | 2 |
| C, rush | 2 | 500 families booking 5 sessions | 127 | 460 | 4,400 | 5,700 | **6,337 (42%)** |

- **The number of web workers is what matters.** At the same load, 4 workers keep the 95th percentile at
  110 ms where 2 workers let it climb to 610 ms (the home page's p99 to 2.4 s). The slowest pages under
  load are the home page (two widgets), the events list and a dojo's dashboard.
- **Logging in takes 250–350 ms**: the password hash is deliberately slow and uses the CPU for that time.
- The few errors in runs B and D are connections that uvicorn closed after 5 idle seconds just as the
  load tool reused them. A browser behind a proxy retries those, so they're an artefact of the test.
- **The rush failed**, for two reasons (below): MySQL ran out of connections (all 151 in use), and the
  sessions overbooked.
- 62 requests a second is far more than the site sees today: it's roughly 300 people clicking around at
  the same moment.

## Load: Celery workers and mail

| Job | On the scaled data | Memory |
|---|---|---|
| Nightly engagement rebuild (`rebuild_engagement`) | 4.9 s, 22,700 rows | mailing child up to 300 MB RSS, then recycled |
| A campaign to every family (6,645 accounts) | queued in 116 s | mailing child 160 MB RSS |
| Sending | 120 mails a minute (`MAILING_BATCH_RATE_LIMIT` 6/m × `MAILING_BATCH_SIZE` 20) | flat |

- **Sending is paced on purpose:** 7,200 mails an hour, so a campaign to 6,600 families takes about 55
  minutes and one to 12,000 about 1 hour 40. Booking and account mail still go first (lower `PRIORITY`),
  so a family's confirmation doesn't wait behind a campaign's queue.
- **But queueing a campaign blocks the single mailing worker** for as long as it takes (2 minutes here,
  about 4 minutes for 12,000 families): booking confirmations queued in that time are sent afterwards.
  Acceptable today; if it isn't, split `queue_mail` into chunks that each run as a task of their own.
- The periodic worker's jobs all take well under a second, so the 10-second mail dispatcher never waits.

## Redis

One Redis holds the cache (db 0), the Channels layer (db 1) and the Celery broker (db 2).

- **It needs very little:** 2.5 MB in use, a peak of 4.4 MB during the load tests, 400 open WebSockets
  included. The cache holds a few lists with a 60-second timeout; the broker holds only waiting tasks
  (mail itself waits in MySQL, not Redis).
- **Its configuration is the risk, not its size.** The devcontainer's Redis has no `maxmemory` and
  `noeviction`: should it ever fill up, it refuses writes, including the broker's, and then no task gets
  queued. Production's settings are unknown. Recommended: `maxmemory 128mb` with `volatile-lru`, so only
  keys with a timeout (the cache, Channels) can be evicted and the broker's queues never are.

## Findings and what to do

In order of urgency.

1. **Simultaneous sign-ups overbook a session** (correctness). `events.views.event_signup` reads the
   highest position and the number of confirmed places, then inserts, without a lock. In the rush, four of
   the five sessions of 22 places confirmed 23 to 25 children, and every session had duplicate
   waiting-list positions (9 to 17 each). **Fix:** lock the session's row at the start of the transaction
   (`Event.objects.select_for_update().get(pk=event.pk)`), so sign-ups for one session go one at a time;
   check the waiting-list promotion in `accounts.views.cancel_registration` for the same pattern. Add a
   `TransactionTestCase` with two threads signing up for the last place.
2. **Database connections aren't limited** (availability). Under ASGI, Django runs every request in a
   thread of its own with its own database connection, and uvicorn accepts any number of requests at once.
   2 web workers opened more than 150 connections during the rush, MySQL's limit, and then every request
   failed. A shared hosting database may allow far fewer per user. **Fix:** cap the requests each worker
   handles at once, e.g. a small ASGI wrapper in `website/asgi.py` with an `asyncio.Semaphore` (20 per
   worker); requests beyond it wait instead of failing. Level27 manages the gunicorn command, so uvicorn's
   own `--limit-concurrency` isn't available to us. Ask Level27 for the connection limits
   ([below](#questions-for-level27)).
3. **Mail text is kept forever** (growth). Build the `mail_content` retention (clear subject, body and
   address after 12 months) in the daily retention job: about a quarter less database after five years.
4. **Four web workers** (`WEB_CONCURRENCY`) if the account's memory allows: much better response times under
   load for about 200 MB more.
5. **Redis limits:** set `maxmemory` and `volatile-lru` on production (or confirm what it has).
6. **Campaign queueing blocks the mailing worker** for a few minutes (see above): acceptable now, chunk it
   when campaigns get bigger.
7. *Development only:* two copies of both Celery workers were running in the devcontainer (one pair from an
   earlier `start.sh`), so every scheduled job ran twice. Stopped on 30 September; `pgrep -af "celery -A website worker"`
   should show five processes.

## Watching production

The `monitoring` app measures the site from the inside; nothing needs installing on the server.

- **`/metrics/`** (Prometheus text format, `monitoring/views.py`): only with `METRICS_TOKEN` as a bearer
  token (`Authorization: Bearer ...`; no token configured = 404). It shows counts and sizes, never anyone's
  data. Point any Prometheus-compatible collector at it once a minute (e.g. Grafana Cloud's free tier, or
  an uptime service that reads Prometheus metrics). What it holds:
  - per table: rows and bytes (`coderdojo_db_table_*`); MySQL's open connections, most used, limit,
    queries and slow queries;
  - Redis: memory, peak, limit, evictions, clients, keys per db;
  - the Celery queues' length, the mail queue (pending, oldest due), open WebSockets;
  - per process (web workers, Celery children, their parents and beat): RSS, PSS and peak RSS,
    reported by each process itself at most once a minute;
  - per view: requests, time, 5xx and a duration histogram; per Celery task: runs, time, failures and the
    longest run.
- **Slow requests** (over `METRICS_SLOW_REQUEST_MS`, 1 second) are logged as warnings with the view name.
- **A daily sample** (`monitoring.CapacitySample`, beat job `capacity-sample` at 02:30) stores the same
  figures in the database, so growth shows as a trend without any outside service. Read them in the Django
  admin, or compare with the projection: `manage.py capacity_report` (read-only, fine on production).
- **`/health/`** stays the uptime check (200 or 503).

**When to act:**

| Signal | Threshold | Likely cause |
|---|---|---|
| `coderdojo_mysql_threads_connected` | over 70% of `coderdojo_mysql_max_connections` | a rush (finding 2) |
| p95 from `coderdojo_http_request_duration_ms_bucket` | over 1 s for 10 minutes | too few web workers |
| sum of `coderdojo_process_pss_bytes` | over 80% of the account's memory | more workers than memory |
| `coderdojo_redis_used_memory_bytes` | over 50% of `maxmemory`, or `evicted_keys` rising | Redis limits (finding 5) |
| `coderdojo_celery_queue_length{queue="celery"}` | over 500 for 30 minutes (a campaign is fine) | a stuck mailing worker |
| `coderdojo_mail_oldest_due_seconds` | over 1,800 (also in `/health/`) | workers down |
| database size (daily sample) | growing faster than the scenario's projection | more mail than planned |

## Questions for Level27

To fill in the budget above (the versions are already asked in `MAINTENANCE.md`, "Still to confirm"):

1. How much memory and how many CPU cores the account gets, and whether it's a hard limit.
2. MySQL's `max_connections` and `max_user_connections`, whether MySQL runs on the same machine (and so in
   our memory), and the disk quota for the database, its binary logs and backups.
3. Redis's `maxmemory` and `maxmemory-policy`, and whether this Redis is ours alone.
4. Whether systemd user units may use the memory controller (`MemoryMax=`), for a hard cap per worker.
5. Whether the gunicorn command could take `--limit-concurrency` or a config file (finding 2).

## Measuring again

In the devcontainer's workspace. The scaled database is a `test_` database, which the app user may
create, and every step leaves the dev data alone.

```sh
# 1. A database at scale (a few minutes)
python -c "import MySQLdb; MySQLdb.connect(host='db', user='coolregistration', passwd='<DB_PASSWORD>').cursor().execute('CREATE DATABASE test_capacity')"
DB_NAME=test_capacity python manage.py migrate
DB_NAME=test_capacity python manage.py seed_scale --scenario growth --years 1

# 2. Bytes per row, then the projection (commit monitoring/row_sizes.json)
DB_NAME=test_capacity python manage.py capacity_report --measure
python manage.py capacity_report

# 3. A production-like run on it, on Redis dbs of its own and without real mail
export DB_NAME=test_capacity DEBUG=false SILK=false SECURE_COOKIES=false EMAIL_HOST= \
       REDIS_CACHE_DB=4 REDIS_CHANNELS_DB=5 CELERY_BROKER_DB=6 MAILING_BOUNCE_IMAP_HOST= METRICS_TOKEN=loadtest
gunicorn -k uvicorn.workers.UvicornWorker main:app -b 127.0.0.1:8001 -w 4 &
celery -A website worker -n periodic-load@%h -Q periodic -c 1 -B --scheduler django_celery_beat.schedulers:DatabaseScheduler --max-tasks-per-child 100 --max-memory-per-child 200000 &
celery -A website worker -n mailing-load@%h -Q celery -c 1 --max-tasks-per-child 100 --max-memory-per-child 200000 &

# 4. Load (Locust in a venv of its own: loadtest/requirements.txt)
python manage.py shell -c "exec(open('loadtest/prepare.py').read())" > /tmp/loadtest.json
LOADTEST_DATA=/tmp/loadtest.json locust -f loadtest/locustfile.py --host http://coolregistration.localhost:8001 \
    --headless -u 300 -r 20 -t 4m --csv /tmp/lt/mixed
LOADTEST_MODE=rush LOADTEST_DATA=/tmp/loadtest.json locust ... -u 500 -r 50 -t 2m   # the registration rush
curl -H "Authorization: Bearer loadtest" http://127.0.0.1:8001/metrics/

# 5. Clean up: stop those processes (by pid: `pkill -f` also matches the shell that runs it),
#    drop test_capacity, and empty Redis dbs 4-6.
```

- Use `http://coolregistration.localhost:8001`, not `127.0.0.1`: the session and CSRF cookies are set
  for that domain (`COOKIE_DOMAIN`).
- Measure memory as PSS from `/proc/<pid>/smaps_rollup`, or read `coderdojo_process_pss_bytes` from
  `/metrics/`.
- This skips nginx on purpose: it measures the application. An end-to-end check through the proxy goes
  from the host (CLAUDE.md, "Workflow rules").
