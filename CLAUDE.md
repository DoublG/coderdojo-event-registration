# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Multiple AI agents/sessions may work in this repo. Keep this file authoritative and current: if you change something it describes (settings, workflows, conventions), update the relevant section in the same change rather than leaving it stale for the next agent.

## What this is

A Django site for CoderDojo Belgium: dojo discovery/search, event registration, applications (new dojo / mentor) with a Belgian legal background-check workflow, learning pathways, mentor team pages, and admin-driven account provisioning. No separate frontend build — server-rendered Django templates plus [htmx](https://htmx.org/) for the dynamic bits (see Architecture below), a hand-maintained `core/static/core/{js,css}/bundle.{js,css}` (no bundler/npm in this repo), and vanilla CSS/HTML for anything that doesn't need a server round-trip.

## Workflow rules

- **New features need tests.** Any new view/route, model behavior, or non-trivial function added to this repo should come with a corresponding test in the relevant app's `tests.py` (see `accounts/tests.py`, `dojos/tests.py`, etc. for the established route-test style: status codes, template used, auth/permission gating, and the actual DB effect of a POST). Don't leave a new feature untested on the assumption someone will backfill it later.
- **Keep the end-user docs current.** `docs/` (Sphinx, built with `make html-all` from inside `docs/` — en/fr/nl, see `docs/README.md`; deps in `docs/requirements.txt`) is the help-centre content for families/volunteers/dojo teams — not this file. If a change alters a user-facing flow this documents, update the relevant `docs/source/**/*.rst` page **and** its French/Dutch translations (`docs/source/locale/{fr,nl}/LC_MESSAGES/`, see `docs/README.md` for the extract/update workflow) in the same change. It intentionally only documents flows that are actually wired up end-to-end — see the note in `docs/source/dojo-team/running-a-session.rst` for what to do once dashboard attendance-marking is implemented.

## Commands

Two ways to run this: directly against the host Python/MySQL, or inside `.devcontainer/` (nginx + TLS on `coolregistration.localhost`, containerized MySQL, Redis, Mailtrap). `website/settings.py` reads `DB_*`/`REDIS_*`/`EMAIL_*`/`COOKIE_DOMAIN` env vars with host-friendly defaults, so the same commands work either way — env vars set by `.devcontainer/docker-compose.yml` just override the defaults.

```sh
# Host: activate the venv first
source .venv/bin/activate

# Dev server
python manage.py runserver              # http://127.0.0.1:8000
# Inside the devcontainer workspace, also reachable via https://coolregistration.localhost through nginx

# Migrations
python manage.py makemigrations <app>
python manage.py migrate

# Tests (plain Django test runner — no pytest config in this repo)
python manage.py test                    # all apps
python manage.py test accounts           # one app
python manage.py test accounts.tests.SomeTestCase.test_something   # one test

# Django shell / admin superuser
python manage.py shell
python manage.py createsuperuser

# Translations (LANGUAGES in settings.py: en-us, nl-be, fr-be, de — switching
# mechanism is wired up per-request/session, but no .po catalogs exist yet)
python manage.py makemessages -l nl_BE
python manage.py compilemessages
```

Devcontainer stack (see `.devcontainer/`):

```sh
docker compose -f .devcontainer/docker-compose.yml up -d          # db, redis, proxy, workspace
docker compose -f .devcontainer/docker-compose.yml run --rm workspace python manage.py migrate
docker compose -f .devcontainer/docker-compose.yml exec workspace bash
```

Regenerating the local dev TLS CA/cert for `coolregistration.localhost`: see `.devcontainer/certs/README.md`.

Lint/format — `ruff` (config in `pyproject.toml`; tool itself in `requirements-dev.txt`, not `requirements.txt`):

```sh
pip install -r requirements-dev.txt
ruff check .              # lint
ruff format .             # format
```

No CI (`.github/workflows` doesn't exist) — these run locally only, on demand.

The devcontainer's `db` service auto-grants its app user rights on Django's `test_<DB_NAME>` database via `.devcontainer/db-init/01-grant-test-db.sql` (runs once, on a fresh volume, via MySQL's `docker-entrypoint-initdb.d`), so `manage.py test` works there with no setup. Outside the devcontainer (a plain host-based MySQL), Django's test runner needs `CREATE`/`DROP DATABASE` on `test_<DB_NAME>`, which a DB user only ever granted rights on its own named database won't have — grant it once: `GRANT ALL PRIVILEGES ON \`test_<DB_NAME>\`.* TO '<DB_USER>'@'%';`.

## Architecture

### Apps and what owns what

- **`accounts`** — the `User` model and everything auth-related.
- **`dojos`** — `Dojo`, `Mentor` (team pages), geo-search.
- **`events`** — `Event`, `Registration`, awards (attendance badges/wristbands).
- **`applications`** — public "start a dojo" / "become a mentor" forms and the admin-side approval + background-check + account-provisioning workflow.
- **`pathways`** — the learning-track catalog (`Pathway`, `PathwayStep`, `PathwayProject`, `Skill`); read-mostly, no user-facing enrollment state.
- **`content`** — `FAQ`, `Testimonial`, `Announcement`, each optionally scoped to a Dojo/Event/Pathway or global when the scoping FK(s) are blank.
- **`notifications`** — a minimal per-user `Notification` model (no views/urls of its own — read directly by whatever renders it).
- **`geo`** — `AdministrativeBoundary` / `Municipality` reference data, the Nominatim geocoding client, and the custom `DistanceSphere` GIS function (see below). No urls.py.
- **`core`** — the homepage view (composes widgets from `dojos`/`events`/`pathways`/`content`) and shared templates/static (`core/templates/core/menu.html` nav, `bundle.js`/`bundle.css`).
- **`website`** — settings/urls/wsgi only.

Each app with URLs owns its own `urls.py`, included from `website/urls.py` with an empty prefix (`path("", include("dojos.urls"))` etc.) — routes live at the top level, not namespaced under `/dojos/`, `/events/`, etc.

### Account model: multi-table inheritance for roles

`accounts.User` (`AUTH_USER_MODEL`) is the base; `DojoOwner`, `Guardian`, `ChildAccount`, `HelperAccount` each subclass it via Django multi-table inheritance rather than a `role` field. A logged-in user's concrete role is discovered via the reverse one-to-one accessor (`user.dojoowner`, `user.guardian`, ...), which raises `DoesNotExist` if that's not their role — `accounts.context_processors.user_roles` does this with `getattr(request.user, "dojoowner", None)` to expose `user_dojo_owner`/`user_guardian` to every template without each view repeating the lookup. `events.Award`/`MilestoneAward`/`BadgeAward` uses the identical inheritance pattern for a different reason (shared base fields, two disjoint award kinds).

`Participant` (a child/ninja) is a plain model, *not* a User subclass — a participant only gets a login (`ChildAccount`, linked via `Participant.account`) if their guardian opts them in; most don't have one.

`dojos.Mentor` is the join point between the public team-page profile and *whichever* of the four account types actually holds that person's login: at most one of `owner_account`/`helper_account`/`guardian_account`/`child_account` may be set (enforced in `Mentor.clean()`), and the `LEAD_COACH` role specifically *requires* `owner_account` to be set to that mentor's own dojo's owner. Read the `Mentor` docstring in `dojos/models.py` before changing role/account logic here — it's non-obvious and easy to get wrong.

Dojo owners and helpers never set their own initial password: `accounts.provisioning.provision_account()` creates the account with a random temp password and `must_change_password=True`, emails it, and `accounts.middleware.ForcePasswordChangeMiddleware` redirects every authenticated request from such a user to the password-change form until they've replaced it. `accounts.backends.EmailOrUsernameBackend` lets login accept either.

`Guardian` is the one role that *is* self-service (`accounts.views.register_guardian`, `RegisterGuardianForm`) — no admin approval or background check, since a guardian only ever manages their own children (unlike `DojoOwner`/`HelperAccount`, who work directly with other people's kids). Username still comes from the same `accounts.provisioning.unique_username()` helper `provision_account()` uses. The child rows on that form are dynamically numbered by JS (`child_<n>_name` etc., possibly non-contiguous after a "Remove") rather than a Django formset — see `accounts.views._parse_child_rows`.

### Applications → background check → provisioning pipeline

`applications.DojoApplication` and `applications.MentorApplication` both mix in `applications.models.BackgroundCheckMixin`, which tracks Belgium's Article 596.2 criminal-record-extract requirement (`not_requested → requested → submitted → validated/rejected`) through admin actions in `applications/admin.py`:

1. Admin requests the check (`request_background_check`) → `applications.services.send_background_check_request` emails the applicant a link built from `background_check_token`.
2. Applicant uploads the document to `applications.storage.private_storage` — a `FileSystemStorage` pointed at `settings.PRIVATE_MEDIA_ROOT` with `base_url=None`, so it has no public URL; the only read path is the permission-gated view in `applications/views.py`.
3. Reviewer (needs the `applications.can_review_background_checks` permission) validates or rejects it. On validation, the uploaded file is deleted immediately and only the decision + `background_check_expires_at` (now + `BACKGROUND_CHECK_VALIDITY`, 365 days) are kept — the document itself is never retained longer than needed for the decision.
4. Approval (`approve_and_provision_owner` etc.) calls `accounts.provisioning.provision_account` to create the real login.

If you touch this flow, keep the "delete the document, keep only the decision" property — it's deliberate, not an oversight.

### Geo search: MySQL spherical distance

`django.contrib.gis`'s `Distance()` only gets proper spherical/spheroidal math substituted on PostGIS — on MySQL it silently returns a raw planar-degree value. `geo/functions.py` defines `DistanceSphere`, a `GeoFunc` subclass wrapping MySQL's `ST_Distance_Sphere`, so the real distance is still computed in the database rather than in Python. **Always use `geo.functions.DistanceSphere` for any new distance-based query against `PointField`s — never Django's built-in `Distance()`, and never compute distance in Python.** See `dojos/search.py` (`dojos_by_distance`) for the reference usage: annotate with `DistanceSphere(F("location"), origin) / 1000.0` and order by it.

The dojo-finder search (`dojos/search.py`) resolves an "origin" point with a fixed priority: typed address (geocoded via `geo.geocoding.geocode`, a thin Nominatim/OpenStreetMap client restricted to Belgium) > browser-supplied lat/lon ("use my location") > a hardcoded Ghent default. It's shared by both the full dojo-finder page and the homepage's embedded widget — `core.views.home` calls the same `resolve_search_origin`/`dojos_by_distance` helpers.

### htmx widgets, not a JS SPA

Per-project convention: reach for htmx for anything that needs server-driven partial updates; use native HTML/CSS for pure client-side behavior (toggles, etc.); only hand-write JS when neither covers it (hardware APIs, instant local state, scroll/viewport-only logic). `core.views.home` is the clearest example — it renders initial state for two independent htmx-driven widgets that each re-fetch themselves against their own endpoint rather than the page reloading:
- **Dojo finder** (`dojos.views`, form in `dojos/forms.py`) — searches post to a widget view that re-renders just the results partial.
- **Upcoming sessions carousel** (`events.views.upcoming_sessions_widget`, paged via `events.search.upcoming_available_events` / `WIDGET_PAGE_SIZE`) — further pages lazy-load over htmx as it's scrolled.

### Email

`send_mail(..., from_email=settings.DEFAULT_FROM_EMAIL, ...)` is called directly from `applications.services` and `accounts.provisioning` (no templated email system/queue). `EMAIL_BACKEND` is env-driven in `website/settings.py`: console backend by default (host dev), SMTP once `EMAIL_HOST` is set (the devcontainer points it at a Mailtrap sandbox — see `.devcontainer/docker-compose.yml`).

### Sensitive vs. public media

`MEDIA_ROOT`/`MEDIA_URL` (photos, icons, event images) are public and served directly under `DEBUG` (`website/urls.py`). `PRIVATE_MEDIA_ROOT` (background-check documents only) has no corresponding `url()` pattern anywhere — don't add one. If a new feature needs to store a sensitive file, use `applications.storage.private_storage` (or the same `base_url=None` pattern) and gate reads through a permission-checked view, not a media URL.

### i18n

`LocaleMiddleware` is wired up (session-stored locale, language switcher in `core/templates/core/menu.html` via `django.conf.urls.i18n`'s `set_language`) for `en-us`/`nl-be`/`fr-be`/`de`, but no `.po` translation catalogs exist yet — the switching mechanism works, the actual translations are a separate follow-up.
