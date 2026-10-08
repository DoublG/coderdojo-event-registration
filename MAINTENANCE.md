# Maintenance: versions, updates, vulnerabilities and audits

How the platform stays supported and secure: which versions run where and until when, how to update,
how to react to a vulnerability, and how the code is audited. For developers and whoever runs the
platform. Conventions for changing the code are in [`CLAUDE.md`](CLAUDE.md); deploying is in its
"Deploying (Level27)" section. How big the database gets and how much memory each component needs is in
[`CAPACITY.md`](CAPACITY.md).

**Last checked: 8 October 2026.** Dates from [endoflife.date](https://endoflife.date), the
[Django roadmap](https://www.djangoproject.com/download/) and [PEP 790](https://peps.python.org/pep-0790/).
Review this page every quarter (see [Calendar](#calendar)) and whenever a version changes.

---

## Versions and support

*Security until* is the last day a version gets security fixes; after that it is end of life (EOL).
*Bugfixes until* is when regular maintenance stops (security fixes only after that).

### Production (Level27, `c40a7b15f.l27powered.eu`)

| Component | Version | Released | Bugfixes until | Security until | Status and action |
|---|---|---|---|---|---|
| Operating system | Ubuntu 22.04.5 LTS | Apr 2022 | ended Sep 2024 | **1 Jun 2027** (Ubuntu Pro/ESM to Apr 2032) | Plan the move to 24.04 LTS (to May 2029) or 26.04 LTS (to May 2031) with Level27 **before June 2027**. |
| Python | 3.14.7 (pyenv `py10102-3.14.7`) | 7 Oct 2025 | 1 Oct 2027 | **31 Oct 2030** | Current. Take each 3.14.x patch release. |
| Django | 6.1.1 | 5 Aug 2026 | 30 Apr 2027 | **31 Dec 2027** | Upgrade to **6.2 LTS** (Apr 2027, security to Apr 2030) between May and Dec 2027. |
| MySQL server | 8.4.11 | Apr 2024 (8.4 LTS) | Apr 2029 | **30 Apr 2032** | Current LTS, the same as development and the CI (checked 6 Oct 2026 from the server's connection greeting, no login needed). |
| MySQL client library | 8.0.46 (`libmysqlclient.so.21`, Ubuntu 22.04's package) | Apr 2018 (8.0) | ended Apr 2025 | **ended 30 Apr 2026** upstream | What `mysqlclient` links against; it talks to the 8.4 server fine. Its development headers (`libmysqlclient-dev`) are now present too (confirmed 8 Oct 2026: `mysqlclient` 2.3.0 built and working). Moves with the operating system's upgrade. |
| Redis (Celery broker, cache, Channels) | 8.10.1 | | | | Running (confirmed 8 Oct 2026, `redis-cli INFO server`); `maxmemory` 512 MB, policy `allkeys-lru` — see [`LEVEL27_QUESTIONS.md`](LEVEL27_QUESTIONS.md), it should be `volatile-lru`. Much newer than the devcontainer's `redis:7.2`; worth trying 7.2 → 8.x in development to match. |
| gunicorn / uvicorn | 26.2.0 / 0.53.0 | | | | No fixed support windows: stay on the latest release. |

### Development (the devcontainer)

| Component | Version | Security until | Status and action |
|---|---|---|---|
| Workspace image | `python:3.14-trixie` (Debian 13), Python 3.14.7 | Debian 13: to **Jun 2030** (LTS) | Current. Rebuild the image for new Python patch releases. |
| MySQL | `mysql:8.4` (8.4.11), on volume `db-data-8.4` | 8.4 LTS: **30 Apr 2032** | Current; production runs the same (8.4.11, confirmed 6 Oct 2026). The same image as the CI. |
| Redis | `redis:7.2` (7.2.16) | 7.2: 1 Dec 2029 | Current. Match production's version once it's confirmed (see [below](#still-to-confirm)). The same image as the CI. |
| nginx | `nginx:1.30-alpine` (1.30.5) | 1.30 stable: until the next stable (about April 2027) | Current. Move to the next stable when it's out. Development only. |
| Mailpit, phpMyAdmin, 2FAuth | `latest` | | Development only; fine on `latest`. |
| Prometheus | `prom/prometheus:v3.13.2` | 3.13 LTS: **31 Jul 2027** | Current LTS. Development only, in the `monitoring` profile (off unless `COMPOSE_PROFILES=monitoring`). Take its patch releases; move to the next LTS before July 2027. |
| Grafana | `grafana/grafana:13.2.0` | 13.2: until the minor after next is out (no date published yet) | Current. Development only, in the `monitoring` profile. Move to the newest minor every few months. |

Development should run the versions production runs (or will run next), so upgrades are tried there
first. Prefer a pinned tag (`mysql:8.4`) over `latest`: a `latest` image is pulled once and then never
moves, so it silently ages.

**When an image version changes, update this table in the same change**: an `image:` tag in
`.devcontainer/docker-compose.yml`, the `FROM` line of `.devcontainer/dockerfile_workspace/Dockerfile`, or the
MySQL and Redis services in `.github/workflows/tests.yml`, `quality.yml` and `audit.yml` (which stay on the devcontainer's
versions). Fill in the new version, its security-until date and the status, and set *Last checked* when you
looked the dates up.

### Python packages

Everything the site imports is pinned in [`requirements.txt`](requirements.txt) (production) and
[`requirements-dev.txt`](requirements-dev.txt) (development tools on top). Most have no support
calendar: stay on the latest release. Watch these:

| Package | Pinned | Note |
|---|---|---|
| Django | 6.1.1 | Take every 6.1.x release (security fixes come as patch releases). See the table above for 6.2 LTS. |
| django-two-factor-auth | 1.18.1 | Officially supports Django up to 5.2; we run and test it on 6.1. Check its release notes on every Django upgrade. |
| django-oauth-toolkit | 3.4.1 | Officially lists Django up to 6.0; tested here on 6.1. Its `oauthlib` has an open advisory (see [Security log](#security-log)). |
| celery, kombu, channels, channels-redis | 5.6.3, 5.6.2, 4.3.2, (see file) | Upgrade together with Redis. |
| mysqlclient | 2.3.0 | Needs the MySQL client headers on the server; present since at least 8 Oct 2026 (see "Missing on the server"). |
| nh3, django-permissions-policy | 0.3.7, 4.34.0 | Security: the Markdown allowlist and the Permissions-Policy header. Keep them current. |
| coverage, radon (mando, colorama) | 7.16.2, 6.0.1 (0.7.1, 0.4.6) | Development only (`requirements-dev.txt`): test coverage and complexity ([`CODING_STANDARDS.md`](CODING_STANDARDS.md)). `pip-audit`: no known vulnerabilities (1 Oct 2026). |
| import-linter, grimp (rich, markdown-it-py, mdurl) | 2.15, 3.17 (15.0.0, 4.2.0, 0.1.2) | Development only (`requirements-dev.txt`): the layers between the apps (`lint-imports`, [`CODING_STANDARDS.md`](CODING_STANDARDS.md), "Layers"), also in the Code audit workflow. `pip-audit`: no known vulnerabilities (2 Oct 2026). |
| mypy, django-stubs (django-stubs-ext, mypy_extensions, pathspec, librt, ast_serialize, types-PyYAML) | 2.4.0, 6.1.2 (6.1.2, 1.1.1, 1.1.1, 0.16.0, 0.12.1, 6.0.12.20260906) | Development only (`requirements-dev.txt`): type checking ([`CODING_STANDARDS.md`](CODING_STANDARDS.md), "Type checking"), also the Code audit's `types` job. django-stubs follows Django's releases (6.1.0 came out two days after Django 6.1); keep its version on our Django's minor. `pip-audit`: no known vulnerabilities (6 Oct 2026). |
| unittest-xml-reporting, lxml | 4.0.0, 6.1.3 | Development only (`requirements-dev.txt`): the test results as JUnit XML for the Tests workflow's summary. `pip-audit`: no known vulnerabilities (1 Oct 2026). |
| locust, matplotlib | 2.46.6, 3.11.2 | The load test and its charts ([`loadtest/requirements.txt`](loadtest/requirements.txt), [`CAPACITY.md`](CAPACITY.md)), in a venv of their own: never in the image or on production. `pip-audit -r loadtest/requirements.txt`: no known vulnerabilities (30 Sep 2026). |

### Missing on the server

Found on 6 Oct 2026 with a read-only check over SSH (`scripts/deploy.sh --check` and an inventory); asked of
Level27, since the account has no root. **Re-checked 8 Oct 2026: items 1–4 and most of 7 are resolved** —
Level27 (or we, for 7) sorted them within two days. What's still open is tracked in
[`LEVEL27_QUESTIONS.md`](LEVEL27_QUESTIONS.md), not duplicated here.

1. ~~The MySQL client development headers~~ — present (`libmysqlclient-dev` 8.0.46), `mysqlclient` builds
   and works.
2. ~~GDAL, GEOS and PROJ~~ — present (GDAL 3.4.1, GEOS 3.10.2, PROJ 22); `django.contrib.gis` works
   (`geo.functions.DistanceSphere` imports and queries fine).
3. ~~A running Redis~~ — running (8.10.1), but with `maxmemory` 512 MB and `maxmemory-policy allkeys-lru`,
   not the `volatile-lru` our caching design assumes ([`LEVEL27_QUESTIONS.md`](LEVEL27_QUESTIONS.md) #1).
4. ~~The worker component *celery*~~ — present, both workers running and answering pings.
5. ~~gunicorn started in `~/app`~~ — confirmed 8 Oct 2026 (`scripts/deploy.sh --check`): gunicorn runs
   in `~/app` with no `-c` of its own, so `gunicorn.conf.py`'s cap is read and active (production was
   briefly on daphne, with no equivalent cap, from 6 to 8 Oct 2026). See
   [`LEVEL27_QUESTIONS.md`](LEVEL27_QUESTIONS.md) for why the cap's current numbers (3 workers × 25)
   still don't reconcile with MySQL's real connection limit.
6. **The proxy's request body limit at 12 MB** — still unconfirmed
   ([`LEVEL27_QUESTIONS.md`](LEVEL27_QUESTIONS.md) #2).
7. **Ours:** ~~the server's `.env` lacks `SITE_URL`, the `MAILING_BOUNCE_*` settings, `SECURE_SSL_REDIRECT`,
   `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `METRICS_TOKEN`~~ — all those keys are now in
   `~/app/.env` (confirmed 8 Oct 2026). `SECURE_HSTS_SECONDS` is at 3600 (1 hour, the first step of the
   Security log's 30 Sep 2026 entry); `SECURE_SSL_REDIRECT` is still `false` and `MAILING_BOUNCE_ADDRESS`/
   `MAILING_BOUNCE_IMAP_HOST` are still empty — raising those further is ours to do, not Level27's.

Present: Ubuntu 22.04.5, Python 3.14.7, `gcc`/`make`/`pkg-config`, MySQL 8.4.11, 64 GB of memory and 12 cores
(shared), 116 GB free disk (8 Oct 2026; was 136 GB on 6 Oct — watch this, the volume is at 93% used).

### Still to confirm

- ~~The production database server's version~~ **Confirmed 6 Oct 2026: MySQL 8.4.11** (8.4 LTS).
- ~~The production Redis version~~ **Confirmed 8 Oct 2026: Redis 8.10.1** — much newer than the
  devcontainer's `redis:7.2.16`; try 8.x in development to match (update
  `.devcontainer/docker-compose.yml` and the CI workflows' Redis service together).
- **Who patches what on the server** — still open, see [`LEVEL27_QUESTIONS.md`](LEVEL27_QUESTIONS.md) #6.

---

## Calendar

| When | What |
|---|---|
| Every week (5 minutes) | Read the security announcements (see [Sources](#sources-to-watch)) and the GitHub Dependabot alerts. |
| Every month | Run the [update check](#routine-updates): `pip-audit`, outdated packages, Django patch release. Deploy what's safe. |
| Every quarter | Review the tables on this page against endoflife.date; bump the *Last checked* date. Run the [code audit](#code-audits) checks. |
| Every quarter | Measure test coverage and complexity again ([`CODING_STANDARDS.md`](CODING_STANDARDS.md), "Measuring again") and look at what dropped. |
| Every quarter | Compare the database's growth (the daily capacity samples, `manage.py capacity_report`) with the projection in [`CAPACITY.md`](CAPACITY.md). |
| Every year | A deeper [security review](#code-audits) of the code and of access to production. |
| Every year | Measure capacity again ([`CAPACITY.md`](CAPACITY.md), "Measuring again") and update its figures. |
| **Now (Sep 2026)** | Confirm the production database and Redis versions; move MySQL off 8.0; pin the devcontainer images. |
| **Oct 2026** | Python 3.15 is released (1 Oct): no action, 3.14 is supported to 2030. |
| **Apr–Dec 2027** | Django 6.2 LTS is out in April: upgrade before 6.1's security support ends (31 Dec 2027). |
| **Before Jun 2027** | Ubuntu 22.04's standard security support ends (1 Jun 2027): the server moves to 24.04 or 26.04 LTS. |
| Oct 2030 | Python 3.14 reaches end of life: be on a newer Python well before. |

---

## Routine updates

Monthly, inside the workspace container, from the repo root:

```sh
pip install pip-audit                        # once
pip-audit -r requirements.txt                # known vulnerabilities in what production runs
pip list --outdated                          # what has a newer release
```

For each update:

1. **Read the release notes**, especially for a new major or minor version (deprecations, dropped
   support, changed defaults). For Django, also the "backwards incompatible changes" section.
2. **Change the pin** in `requirements.txt` (or `requirements-dev.txt` for a development tool), then
   `pip install -r requirements-dev.txt` in the container (or rebuild it).
3. **Run everything:** `python manage.py test`, `ruff check .`, `python manage.py makemigrations --check`
   (an upgrade can need a migration), and click through the pages the package touches. Run the tests
   with warnings on (`python -W error::DeprecationWarning manage.py test <app>`) before a Django upgrade.
4. **Deploy:** `scripts/deploy.sh --check`, then `scripts/deploy.sh`. The deploy runs `manage.py check`
   on the new code before touching the live site, and restarts the Celery workers.
5. **Update this page** when a row changes.

Patch releases (6.1.1 → 6.1.2) are safe to take quickly. Minor and major versions (Django 6.1 → 6.2,
Celery 5 → 6) get their own change, tested on the devcontainer first. Never upgrade on production only.

**Django upgrades** follow Django's own advice: first the latest patch of the current version with
deprecation warnings fixed, then the next version. Check that django-two-factor-auth, django-otp,
django-oauth-toolkit, django-auditlog, django-ninja, channels and django-celery-beat support it; the
test suite runs all of them.

**Python upgrades** (3.14 → 3.15): a new pyenv environment on the server (`deploy.sh` installs into the
one gunicorn runs from, see CLAUDE.md), the devcontainer's base image, and the Celery worker
component's commands in the Level27 panel, which run `celery` from the PATH of that environment.

**Operating system, MySQL and Redis** upgrades on production go through Level27. Try the new versions
in the devcontainer first by changing the image tags in `.devcontainer/docker-compose.yml`.

**Changing the devcontainer's MySQL version.** A MySQL can't open data written by a newer version, so
the database volume is named after the version (`db-data-8.4`): a new version gets a new volume, and
`start.sh` seeds it. To keep your data instead, dump it before switching and load it into the new one:

```sh
docker exec coolregistration-dev-db mysqldump -uroot -pcoolregistration --single-transaction \
    --routines --triggers --no-tablespaces --set-gtid-purged=OFF --databases coolregistration > dev-db.sql
# change the image and the volume name in docker-compose.yml, `up -d`, wait until MySQL is up, then:
docker exec -i coolregistration-dev-db mysql -uroot -pcoolregistration < dev-db.sql
```

Load it before `start.sh` runs, or it seeds the empty database first. The old volume stays until you
remove it (`docker volume ls`, `docker volume rm <project>_db-data`).

---

## Responding to a vulnerability

### Sources to watch

- **Reports from outside:** [`SECURITY.md`](SECURITY.md) asks people to report through GitHub's private
  vulnerability reporting or by mail to erik@woidt.be (for now, until an organisation address takes over), and promises an acknowledgement within
  3 working days and the fix times below. Keep the two in step.
- **Django:** the security announcements on the [Django weblog](https://www.djangoproject.com/weblog/)
  and the `django-announce` mailing list. Django pre-announces security releases a week ahead.
- **Python:** [python.org security](https://www.python.org/dev/security/) and the release announcements.
- **Our dependencies:** GitHub's **Dependabot alerts** for this repository (Settings → Code security →
  enable *Dependabot alerts*; free for public repositories), and `pip-audit`.
- **Server:** Ubuntu security notices ([USN](https://ubuntu.com/security/notices)), MySQL and Redis
  advisories, and whatever Level27 sends.

### Triage

For every advisory, first ask: **is the vulnerable code reachable in our setup?** Check which feature it
is in and whether we use it (for example, the open oauthlib advisory is in the authorization-code flow,
which our API doesn't offer). Then:

| Severity (in our setup) | Examples | Fix within |
|---|---|---|
| Critical | Remote code execution, authentication bypass, access to children's data, criminal-record extracts or health notes | 24–48 hours, outside the monthly routine |
| High | Privilege escalation between roles, cross-site scripting on a logged-in page, SQL injection | 7 days |
| Medium | Denial of service, information leaks without personal data | The next monthly update (30 days) |
| Low, or not reachable here | A feature we don't use | Record it in the [Security log](#security-log); fixed with the next regular upgrade |

### Fixing

1. Update the package (see [Routine updates](#routine-updates)), or apply the advisory's workaround if no
   fixed version exists yet.
2. Run the full test suite and `pip-audit` again.
3. Deploy with `scripts/deploy.sh`.
4. Record it in the [Security log](#security-log): what, when found, assessment, when fixed.

### If personal data may have leaked

1. **Contain:** take the affected feature offline (or the site), revoke what may be compromised.
2. **Rotate secrets** that may be exposed: `SECRET_KEY` and the database, Redis and mail passwords in
   `~/app/.env` on the server (a new `SECRET_KEY` logs everyone out and invalidates password-reset and
   login links); the dojos' API client secrets (*Renew secret* on each dojo's API page, or
   `api.services.renew_secret`); and SSH keys.
3. **Find out what happened** with the audit log (who changed or viewed what; the organisation dashboard's
   *Audit log*, or the Django admin's) and the server logs.
4. **Notify within 72 hours:** under GDPR art. 33, a breach of personal data is reported to the Belgian
   Data Protection Authority ([GBA/APD](https://www.dataprotectionauthority.be)) within 72 hours of
   becoming aware of it, unless it's unlikely to harm anyone. Most data here is about children, so assume
   it must be reported. When the risk to people is high (art. 34), tell the families too.
5. **Record** the breach, its effects and the measures taken (GDPR art. 33.5), even when it wasn't reported.

---

## Code audits

### On every change (already in place)

Two GitHub Actions workflows run these on every push (the *Actions* tab; a failed run is also mailed to
whoever pushed):

- **Tests** (`.github/workflows/tests.yml`): the test suite (about 1,190 tests), against MySQL 8.4 and
  Redis 7.2, and `makemigrations --check`. It includes guard tests that fail when new code forgets a rule:
  every field has a privacy classification, every model an audit-log decision, every model is fully usable
  in the admin, the API's schema never exposes sensitive fields, no page loads scripts from another site.
  Its results show on the run's page (a summary per app, the failed tests with their traceback, the slowest
  tests), each failed test is marked on the line where it failed, the JUnit XML is kept 30 days as the
  run's `test-results` artifact, and the README's badge shows main's latest result.
- **Code audit** (`.github/workflows/audit.yml`, on pushes to main and pull requests, and **every Monday**,
  since new advisories appear without any change here):
  - `ruff check .` and `ruff format --check .` (lint and formatting);
  - `lint-imports`, the layers between the apps (`pyproject.toml`, [`CODING_STANDARDS.md`](CODING_STANDARDS.md));
  - `ruff check --extend-select S .`, the flake8-bandit security rules. Tests, seed commands and
    `user-journeys/` are left out (`pyproject.toml`); a reviewed line on the site carries
    `# noqa: Sxxx` with its reason;
  - `pip-audit` over `requirements.txt` and `requirements-dev.txt`. An advisory that isn't reachable here
    is ignored there (`--ignore-vuln`) only together with its row in the [Security log](#security-log);
  - `manage.py check --deploy` with DEBUG off: errors fail the run, warnings are listed in the run's
    summary;
  - **CodeQL** (Python and JavaScript, the `security-extended` queries): its findings are in the
    repository's *Security → Code scanning*, where a false positive is dismissed with its reason.
- Turn on **Dependabot alerts** too (Settings → Code security): they warn about a new advisory the day it
  is published, between the Monday runs.
- **Access goes through helpers** (`dojos.access`, `accounts.organisation.require_area`), never ad hoc
  checks: a review looks for views that skip them.
- **Claude Code's `/security-review`** on a change before it's committed, and `/code-review` on a branch.

### Every quarter

```sh
pip-audit -r requirements.txt                          # known vulnerabilities
ruff check --select S .                                # flake8-bandit: security-sensitive patterns
DEBUG=false python manage.py check --deploy            # Django's production security settings
```

The Code audit workflow runs these on every change; once a quarter, look through its latest summary (the
`check --deploy` job now fails on any warning) and the ignored advisories, fix what's real, and
note the rest.

### Every year

A deeper review, by a person with Claude Code's help:

- **Authorization:** every view under `/dojos/<id>/…` goes through `require_dojo_access`, every
  organisation page through `require_area`, the API only reaches the client's own dojo.
- **Sensitive data:** criminal-record extracts (never a public URL, deleted on decision), health notes
  (champion only, logged), the privacy registry's classifications still right.
- **Authentication:** the sign-in policy per role, two-step login, login links, session handling.
- **Access to production:** who has SSH keys, who holds organisation roles and superuser rights, and the
  Django admin access grants in the audit log. Remove what's no longer needed.
- **Dependencies:** packages that aren't needed any more, and ones that stopped being maintained.

---

## Security log

| Found | What | Assessment | Status |
|---|---|---|---|
| 30 Sep 2026 | **oauthlib 3.3.1**, CVE-2026-49265 / GHSA-xpv3-w29h-x7cv (since 1 Oct also PYSEC-2026-4114, which `pip-audit` reports; the workflow's `--ignore-vuln CVE-2026-49265` matches it): timing side channel in PKCE (authorization-code flow). Fixed in 4.0.0. | **Not reachable here:** our API offers only the client-credentials grant (`api/services.py`), which doesn't use PKCE. Low. django-oauth-toolkit 3.4.1 requires `oauthlib>=3.3.0` and doesn't list 4.0 yet. | Open: try oauthlib 4.0.0 with the API tests in the devcontainer; upgrade when django-oauth-toolkit supports it. |
| 30 Sep 2026 | **Markdown links** (`core/templatetags/markdown_extras.py`, `markdownify`): the text is HTML-escaped, but Python-Markdown keeps any link scheme, so `[x](javascript:...)` in a dojo's or event's description becomes a working `javascript:` link on the public page. Found by the Code audit workflow's security rules (S308). | **High** (stored cross-site scripting): any active champion or mentor can put it on a public page, and a logged-in visitor who clicks it runs the script as themselves. No Content-Security-Policy limits it. | **Fixed 30 Sep 2026:** `markdownify` now cleans its HTML with nh3 against an allowlist (headings from `<h2>`, paragraphs, bold, italic, lists, links; links only `http`, `https`, `mailto` or relative, with `rel="nofollow noopener noreferrer"`). Images, code and anything else are dropped. Tests: `core.tests.MarkdownifyTests`. |
| 30 Sep 2026 | **`check --deploy` warnings**: no HSTS, no HTTPS redirect, session and CSRF cookies not `Secure`; django-oauth-toolkit's RFC 9700 defaults (implicit and password grants, tokens in the query string, tokens stored in plain text). Also no Content-Security-Policy or Permissions-Policy. | Medium: TLS ends at Level27's proxy, so the cookies' `Secure` flag and HSTS are cheap to add; the OAuth grants we don't offer weren't reachable, tokens stored in plain text were. A CSP limits what any future cross-site scripting bug can do. | **Fixed in the code 30 Sep 2026** (CLAUDE.md, "Security headers"): `Secure` cookies, the proxy header, all RFC 9700 options (tokens now stored hashed), a strict script CSP with nonces (inline handlers moved to `bundle.js`, htmx without eval), Permissions-Policy. Tested with `core.tests.SecurityHeadersTests`, the API tests and a browser crawl of about 480 pages as six roles. **Partially done on production, confirmed 8 Oct 2026:** `SECURE_HSTS_SECONDS` is now `3600` (the first of the three planned steps — 1 hour, 1 day, 1 year); `SECURE_SSL_REDIRECT` is still `false`, and whether Level27's proxy sets `X-Forwarded-Proto` itself is still unconfirmed (that's the precondition for turning the redirect on safely — see `LEVEL27_QUESTIONS.md`). `deploy.sh` reports both values on every `--check`. |
| 30 Sep 2026 | **MySQL 8.0** (the production client, possibly the server) reached end of life on 30 Apr 2026: no more security fixes. | **The server is 8.4.11** (confirmed 6 Oct 2026); only the client library, Ubuntu 22.04's package, is 8.0. | Server closed. The client library moves with the OS upgrade (before Jun 2027). |
| 30 Sep 2026 | **Devcontainer images** past end of life: MySQL 9.1 (`latest` gone stale), nginx 1.27; the workspace on Debian 12. | Development only, not reachable from outside. | **Fixed 30 Sep 2026:** pinned `mysql:8.4`, `redis:7.2`, `nginx:1.30-alpine`, workspace on `python:3.14-trixie`. The dev data was carried from 9.1 to 8.4 with a dump; the old `db-data` volume is left as a fallback. |
| 8 Oct 2026 | **Documentation drift from production**, found during a documentation review with SSH access to the server: the "Missing on the server" items (MySQL headers, GDAL/GEOS, Redis) from 6 Oct 2026 were resolved within two days without the docs being updated; `mysqlclient` and `django.contrib.gis` work; Redis runs (8.10.1) but as `allkeys-lru`/512 MB, not the assumed `volatile-lru`; `~/app/.env` has all the keys the 6 Oct check said were missing; production's MySQL user has `max_user_connections` = 32, well under the 151 the per-worker concurrency cap was sized against. | **Not a vulnerability, an operational risk:** the connection-exhaustion protection `CAPACITY.md` describes needed the right app server to be in effect, against a real limit tighter than assumed. | Docs corrected 8 Oct 2026. **App server switched from daphne back to gunicorn the same day** (the panel's `website` component, "server: uvicorn" = our `gunicorn -k uvicorn.workers.UvicornWorker`), so `gunicorn.conf.py`'s cap is active again. **Measured, not just calculated, 8 Oct 2026** (`CAPACITY.md`, "Rerun against Level27's real limits": the devcontainer rebuilt to match production's 3 workers and 32-connection limit exactly, then load-tested): today's cap of 25 produces real `500` errors under a rush (not just `503` refusals) and a quarter of the throughput of every other setting; cap 8 eliminates every `500` tested. **Fixed 8 Oct 2026** (release `20261008-110338-8f46815-dirty`): `gunicorn.conf.py`'s default changed from 25 to 8 and deployed via `scripts/deploy.sh --yes`; confirmed live by reading the master process's own environment (`scripts/deploy.sh --check`, fixed the same day to report this truthfully instead of a hardcoded "25" — see below). `SECURE_SSL_REDIRECT` is still `false` on production. |
| 8 Oct 2026 | **`scripts/deploy.sh --check`'s "gunicorn.conf.py: read (concurrency cap N per worker...)" line always said N=25**, regardless of the deployed file's actual default or the running master's real environment — it evaluated `${UVICORN_LIMIT_CONCURRENCY:-25}` in the SSH session's own shell, which never has that variable set (it's never sourced from `.env` into a login shell), so the expansion silently fell through to the hardcoded default every time. Found while verifying the cap-8 fix above: the diagnostic claimed "25" immediately after deploying "8." | **Tooling gave false confidence, not a vulnerability:** anyone trusting this line to confirm a cap change took effect would have been wrong, silently. | **Fixed 8 Oct 2026:** `app_server()` now reads the deployed file's actual default (`grep` on `gunicorn.conf.py`) and separately checks the live master's `/proc/<pid>/environ` for a real override, and reports which one is actually in effect. |
| 8 Oct 2026 | **Static and media files 403'd for every visitor** for at least 7 minutes (09:57–10:04 CEST, likely longer): Apache's error log showed `AH00035: ... search permissions are missing on a component of the path (filesystem path '/var/python/py10102/app')` for every `/static/`, `/media/` and (presumably) `/docs/` request. Cause: switching the app server in the Level27 panel made Level27 reapply the Apache configuration, which reset `~` (the account's home directory) to `750` — stripping the `o+x` bit Apache (running as `www-data`, in no group shared with `py10102`) needs to even traverse into `~/app/staticfiles`/`~/app/media`/`~/docs` to serve them, regardless of the `Require all granted` in the "Extra Apache configuratie" box (that's an authorization check, not a filesystem permission). `scripts/deploy.sh` already runs `chmod o+x "$HOME"` on every deploy for exactly this reason, but that only happens on a code deploy — not on a panel-only change like this one, so the fix lapsed silently. | **Availability, not a data exposure:** every visitor saw an unstyled, broken page until fixed. The underlying "Extra Apache configuratie" (confirmed live in the panel, 8 Oct 2026) is our own config, aliasing `/static/`, `/media/`, `/docs/`, `/_errors/` straight to disk under the home directory — the same pattern the devcontainer's nginx uses for parity. No alternative Level27-managed static-asset location (exempt from the `750` reset) was found; this dependency is structural to the chosen architecture, not a Level27 mistake. | **Fixed 8 Oct 2026** (`chmod o+x ~`, confirmed by fresh `200`s in the access log). **Not yet fixed structurally** — deliberately left as a documented gotcha rather than code changed (decision made 8 Oct 2026): after *any* Level27 panel change (not just a code deploy), re-run `chmod o+x ~` before trusting static/media/docs to load. `scripts/deploy.sh --check` does not currently surface this (it only reports `~`'s permissions, doesn't fail on them). |
