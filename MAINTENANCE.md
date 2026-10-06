# Maintenance: versions, updates, vulnerabilities and audits

How the platform stays supported and secure: which versions run where and until when, how to update,
how to react to a vulnerability, and how the code is audited. For developers and whoever runs the
platform. Conventions for changing the code are in [`CLAUDE.md`](CLAUDE.md); deploying is in its
"Deploying (Level27)" section. How big the database gets and how much memory each component needs is in
[`CAPACITY.md`](CAPACITY.md).

**Last checked: 30 September 2026.** Dates from [endoflife.date](https://endoflife.date), the
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
| MySQL client | 8.0.46 | Apr 2018 (8.0) | ended Apr 2025 | **ended 30 Apr 2026** | **EOL.** The database *server* version is still to confirm (see [below](#still-to-confirm)); move to **8.4 LTS** (security to Apr 2032) or 9.7 LTS (to Apr 2034). |
| Redis (Celery broker, cache, Channels) | to confirm | | | | See [below](#still-to-confirm). |
| gunicorn / uvicorn | 26.2.0 / 0.53.0 | | | | No fixed support windows: stay on the latest release. |

### Development (the devcontainer)

| Component | Version | Security until | Status and action |
|---|---|---|---|
| Workspace image | `python:3.14-trixie` (Debian 13), Python 3.14.7 | Debian 13: to **Jun 2030** (LTS) | Current. Rebuild the image for new Python patch releases. |
| MySQL | `mysql:8.4` (8.4.11), on volume `db-data-8.4` | 8.4 LTS: **30 Apr 2032** | Current; the version production should move to. The same image as the CI. |
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
MySQL and Redis services in `.github/workflows/tests.yml` and `audit.yml` (which stay on the devcontainer's
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
| mysqlclient | 2.3.0 | Needs the MySQL client headers on the server (missing on Level27 today, see CLAUDE.md). |
| nh3, django-permissions-policy | 0.3.7, 4.34.0 | Security: the Markdown allowlist and the Permissions-Policy header. Keep them current. |
| coverage, radon (mando, colorama) | 7.16.2, 6.0.1 (0.7.1, 0.4.6) | Development only (`requirements-dev.txt`): test coverage and complexity ([`CODING_STANDARDS.md`](CODING_STANDARDS.md)). `pip-audit`: no known vulnerabilities (1 Oct 2026). |
| import-linter, grimp (rich, markdown-it-py, mdurl) | 2.15, 3.17 (15.0.0, 4.2.0, 0.1.2) | Development only (`requirements-dev.txt`): the layers between the apps (`lint-imports`, [`CODING_STANDARDS.md`](CODING_STANDARDS.md), "Layers"), also in the Code audit workflow. `pip-audit`: no known vulnerabilities (2 Oct 2026). |
| mypy, django-stubs (django-stubs-ext, mypy_extensions, pathspec, librt, ast_serialize, types-PyYAML) | 2.4.0, 6.1.2 (6.1.2, 1.1.1, 1.1.1, 0.16.0, 0.12.1, 6.0.12.20260906) | Development only (`requirements-dev.txt`): type checking ([`CODING_STANDARDS.md`](CODING_STANDARDS.md), "Type checking"), also the Code audit's `types` job. django-stubs follows Django's releases (6.1.0 came out two days after Django 6.1); keep its version on our Django's minor. `pip-audit`: no known vulnerabilities (6 Oct 2026). |
| unittest-xml-reporting, lxml | 4.0.0, 6.1.3 | Development only (`requirements-dev.txt`): the test results as JUnit XML for the Tests workflow's summary. `pip-audit`: no known vulnerabilities (1 Oct 2026). |
| locust, matplotlib | 2.46.6, 3.11.2 | The load test and its charts ([`loadtest/requirements.txt`](loadtest/requirements.txt), [`CAPACITY.md`](CAPACITY.md)), in a venv of their own: never in the image or on production. `pip-audit -r loadtest/requirements.txt`: no known vulnerabilities (30 Sep 2026). |

### Still to confirm

- **The production database server's version.** The server only shows the MySQL 8.0 *client*. Ask
  Level27, or run on the server: `mysql -h <DB_HOST> -u <DB_USER> -p -N -e 'SELECT VERSION()'`. If it's 8.0,
  it is past end of life: ask Level27 for 8.4 LTS.
- **The production Redis version:** `redis-cli -h <REDIS_HOST> INFO server | grep redis_version`.
- **Who patches what on the server.** On Level27's managed hosting the operating system, MySQL and Redis are
  expected to be theirs to patch, and Python (pyenv) and the Python packages ours. Confirm this with
  Level27 and note it here.

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
one gunicorn runs from, see CLAUDE.md), the devcontainer's base image, and the Celery units in
`scripts/systemd/`, which name the Python path.

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

- **Tests** (`.github/workflows/tests.yml`): the test suite (about 1,000 tests), against MySQL 8.4 and
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
| 30 Sep 2026 | **oauthlib 3.3.1**, CVE-2026-49265 / GHSA-xpv3-w29h-x7cv: timing side channel in PKCE (authorization-code flow). Fixed in 4.0.0. | **Not reachable here:** our API offers only the client-credentials grant (`api/services.py`), which doesn't use PKCE. Low. django-oauth-toolkit 3.4.1 requires `oauthlib>=3.3.0` and doesn't list 4.0 yet. | Open: try oauthlib 4.0.0 with the API tests in the devcontainer; upgrade when django-oauth-toolkit supports it. |
| 30 Sep 2026 | **Markdown links** (`core/templatetags/markdown_extras.py`, `markdownify`): the text is HTML-escaped, but Python-Markdown keeps any link scheme, so `[x](javascript:...)` in a dojo's or event's description becomes a working `javascript:` link on the public page. Found by the Code audit workflow's security rules (S308). | **High** (stored cross-site scripting): any active champion or mentor can put it on a public page, and a logged-in visitor who clicks it runs the script as themselves. No Content-Security-Policy limits it. | **Fixed 30 Sep 2026:** `markdownify` now cleans its HTML with nh3 against an allowlist (headings from `<h2>`, paragraphs, bold, italic, lists, links; links only `http`, `https`, `mailto` or relative, with `rel="nofollow noopener noreferrer"`). Images, code and anything else are dropped. Tests: `core.tests.MarkdownifyTests`. |
| 30 Sep 2026 | **`check --deploy` warnings**: no HSTS, no HTTPS redirect, session and CSRF cookies not `Secure`; django-oauth-toolkit's RFC 9700 defaults (implicit and password grants, tokens in the query string, tokens stored in plain text). Also no Content-Security-Policy or Permissions-Policy. | Medium: TLS ends at Level27's proxy, so the cookies' `Secure` flag and HSTS are cheap to add; the OAuth grants we don't offer weren't reachable, tokens stored in plain text were. A CSP limits what any future cross-site scripting bug can do. | **Fixed in the code 30 Sep 2026** (CLAUDE.md, "Security headers"): `Secure` cookies, the proxy header, all RFC 9700 options (tokens now stored hashed), a strict script CSP with nonces (inline handlers moved to `bundle.js`, htmx without eval), Permissions-Policy. Tested with `core.tests.SecurityHeadersTests`, the API tests and a browser crawl of about 480 pages as six roles. **Open on production:** confirm Level27's proxy sets `X-Forwarded-Proto` itself, then set `SECURE_SSL_REDIRECT=true` and raise `SECURE_HSTS_SECONDS` (1 hour, 1 day, 1 year) in `~/app/.env`; `deploy.sh` reports what's still missing. |
| 30 Sep 2026 | **MySQL 8.0** (the production client, possibly the server) reached end of life on 30 Apr 2026: no more security fixes. | Depends on the server version (to confirm). | Open: confirm with Level27, move to 8.4 LTS. |
| 30 Sep 2026 | **Devcontainer images** past end of life: MySQL 9.1 (`latest` gone stale), nginx 1.27; the workspace on Debian 12. | Development only, not reachable from outside. | **Fixed 30 Sep 2026:** pinned `mysql:8.4`, `redis:7.2`, `nginx:1.30-alpine`, workspace on `python:3.14-trixie`. The dev data was carried from 9.1 to 8.4 with a dump; the old `db-data` volume is left as a fallback. |
