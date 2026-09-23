# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Multiple AI agents/sessions may work in this repo. Keep this file authoritative and current: if you change something it describes (settings, workflows, conventions), update the relevant section in the same change rather than leaving it stale for the next agent.

## What this is

A Django site for CoderDojo Belgium: dojo discovery/search, event registration, applications (new dojo / mentor) with a Belgian legal background-check workflow, learning pathways, mentor team pages, and admin-driven account provisioning. No separate frontend build — server-rendered Django templates plus [htmx](https://htmx.org/) for the dynamic bits (see Architecture below), a hand-maintained `core/static/core/{js,css}/bundle.{js,css}` (no bundler/npm in this repo), and vanilla CSS/HTML for anything that doesn't need a server round-trip.

## Workflow rules

- **Always work inside the `.devcontainer`, never against the host Python/MySQL.** Before running `manage.py` commands (migrations, `runserver`, and especially `manage.py test`), check the stack is actually up — `docker ps` should show `coolregistration-dev-workspace`/`-db`/`-redis`/`-proxy` as `Up`; if it isn't, start it (`docker compose -f .devcontainer/docker-compose.yml up -d`) rather than falling back to a host-level run. Run commands via `docker compose -f .devcontainer/docker-compose.yml exec workspace <command>` (or `exec workspace bash` for a shell). This matters beyond convention: the notification bell's WebSocket support (Django Channels, see Architecture) depends on Redis and on `daphne` actually serving `runserver`'s ASGI app, both of which the devcontainer wires up for you — a host run can silently diverge (e.g. a stray host MySQL, or no Redis at all) without it being obvious from the command output alone.
  - **One exception: testing nginx's own behavior, or any real end-to-end check, has to go through the host.** `docker compose exec workspace` talks to Django directly and never touches the `proxy` container at all — TLS termination, the `/docs/` alias, and (since adding WebSockets) the `Upgrade`/`Connection` proxy headers all live in nginx, not Django, so a workspace-only check can pass while the thing a real client actually hits is still broken. Verify those from the host against the real FQDN (`https://coolregistration.localhost`, `wss://coolregistration.localhost/ws/...`) — plain `127.0.0.1`/internal-port requests skip nginx *and* fail `ALLOWED_HOSTS`/origin checks that key off `coolregistration.localhost`. A hand-written test client also needs to send an `Origin` header matching that FQDN (a real browser always does this automatically) or Channels' `AllowedHostsOriginValidator` (see Architecture) rejects the connection with a 403 that has nothing to do with the thing you're actually testing.
  - **Editing `.devcontainer/nginx/nginx.conf` needs a proxy recreate, not just a save.** It's a single-file bind mount (`docker-compose.yml`), which Docker pins to the file's *inode* — the same gotcha `docs/README.md` already documents for `docs/build/`. An editor/tool that replaces the file (rather than writing in place) leaves the running `proxy` container looking at the old, deleted inode forever; `nginx -s reload` inside it changes nothing because it's reloading that same stale content. Fix: `docker compose -f .devcontainer/docker-compose.yml up -d --force-recreate --no-deps proxy` (the `--no-deps` matters here too, same reason as `docs/README.md`'s note).
- **New features need tests.** Any new view/route, model behavior, or non-trivial function added to this repo should come with a corresponding test in the relevant app's `tests.py` (see `accounts/tests.py`, `dojos/tests.py`, etc. for the established route-test style: status codes, template used, auth/permission gating, and the actual DB effect of a POST). Don't leave a new feature untested on the assumption someone will backfill it later.
- **Keep the end-user docs current.** `docs/` (Sphinx, built with `make html-all` from inside `docs/` — en/fr/nl, see `docs/README.md`; deps in `docs/requirements.txt`) is the help-centre content for families/volunteers/dojo teams — not this file. If a change alters a user-facing flow this documents, update the relevant `docs/source/**/*.rst` page **and** its French/Dutch translations (`docs/source/locale/{fr,nl}/LC_MESSAGES/`, see `docs/README.md` for the extract/update workflow) in the same change. It intentionally only documents flows that are actually wired up end-to-end — see the note in `docs/source/dojo-team/running-a-session.rst` for what to do once dashboard attendance-marking is implemented.

## Commands

Run everything inside `.devcontainer/` (nginx + TLS on `coolregistration.localhost`, containerized MySQL, Redis, Mailtrap) — see the workflow rule above. `website/settings.py` reads `DB_*`/`REDIS_*`/`EMAIL_*`/`COOKIE_DOMAIN` env vars with host-friendly defaults (so a host-level run isn't *broken*, just not what this repo's workflow expects — Redis/Channels behavior in particular can diverge, see above); `.devcontainer/docker-compose.yml` sets the real ones.

```sh
docker compose -f .devcontainer/docker-compose.yml up -d          # db, redis, proxy, workspace — check first with `docker ps`
docker compose -f .devcontainer/docker-compose.yml exec workspace bash    # a shell inside the workspace container
```

From that shell (or prefix any of these with `docker compose -f .devcontainer/docker-compose.yml exec workspace`):

```sh
# Dev server — reachable via https://coolregistration.localhost through nginx
python manage.py runserver 0.0.0.0:8000

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

**A single `User` row can hold more than one of these roles at once** — MTI doesn't prevent it, and nothing here assumes "exactly one." `accounts.provisioning.attach_role(user, role_model, **extra_fields)` is how a role gets added to an *existing* account instead of provisioning a disconnected new one: it copies `User`'s own fields onto a fresh `role_model` instance field-by-field via `getattr`/`setattr`, then saves it (Django's `_save_table` inserts a new child-table row for that pk, or — re-attaching a role the account already has, e.g. a `DojoOwner` starting a second dojo, since `dojos.Dojo.owner` is 1-to-n — harmlessly updates the existing one; never a duplicate-row error). **Never use `role_obj.__dict__.update(user.__dict__)` for this** — it looks equivalent but silently corrupts the account (blanks the password, logs the session out) whenever `user` is `request.user`: that's a `SimpleLazyObject` proxy, and `.__dict__` on it returns the *proxy's own* internal attributes rather than the wrapped `User`'s field values, since `__dict__` access bypasses `__getattr__`. Two self-service entry points use this: `accounts.views.link_guardian_role` (any logged-in account without a Guardian role adds one, mirroring `register_guardian` minus the fields already on `request.user`) and, on the background-checked side, `DojoApplication`/`MentorApplication.applicant_account` — set when an already-logged-in user submits `register_dojo`/`register_helper` — which `approve_and_provision_owner`/`approve_and_provision_helper` check to promote that existing account via `attach_role` instead of `provision_account` (see below).

### Applications → background check → provisioning pipeline

`applications.DojoApplication` and `applications.MentorApplication` both mix in `applications.models.BackgroundCheckMixin`, which tracks Belgium's Article 596.2 criminal-record-extract requirement (`not_requested → requested → submitted → validated/rejected`) through admin actions in `applications/admin.py`. It's mandatory for every applicant in this pipeline — both roles are adults; a younger volunteer (a ninja) would be promoted to a mentor role through a separate flow, not this one, so there's no age check here.

1. Admin requests the check (`request_background_check`) → `applications.services.send_background_check_request` emails the applicant a link built from `background_check_token`. Not limited to first-time requests: re-running this on an application whose check isn't *currently* valid (expired, or never was) is also how a renewal is requested — see step 5.
2. Applicant uploads the document to `applications.storage.private_storage` — a `FileSystemStorage` pointed at `settings.PRIVATE_MEDIA_ROOT` with `base_url=None`, so it has no public URL; the only read path is the permission-gated view in `applications/views.py`.
3. Reviewer (needs the `applications.can_review_background_checks` permission) validates or rejects it. On validation, the uploaded file is deleted immediately and only the decision + `background_check_expires_at` (now + `BACKGROUND_CHECK_VALIDITY`, 365 days) are kept — the document itself is never retained longer than needed for the decision.
4. Approval (`approve_and_provision_owner`/`approve_and_provision_helper`) provisions the account — normally via `accounts.provisioning.provision_account` (mints a new login, temp password emailed), but if the application's `applicant_account` is set (the applicant was already logged in when they applied — see the cross-role note above) it instead promotes that existing account via `attach_role`, no new login/email, just a "you have a new role" notice (`applications.services.send_role_activated_email`). Either way, `background_check_required`/`background_check_expires_at` get copied onto the resulting `accounts.DojoOwner`/`HelperAccount` and it's linked back via `DojoApplication.provisioned_owner`/`MentorApplication.provisioned_helper` — from here on **the account**, not the application, is what gates login (see below).
5. The application row doubles as the account's permanent background-check record rather than a one-time thing: as `background_check_expires_at` nears/passes, an admin re-runs `request_background_check` → applicant re-uploads (also reachable without the emailed link, at `renew_background_check`, if they're already logged in — see below) → reviewer re-validates, and `validate_background_check` pushes the fresh expiry back onto the linked account (`provisioned_owner`/`provisioned_helper`).

If you touch this flow, keep the "delete the document, keep only the decision" property — it's deliberate, not an oversight.

**Renewal disables login until it's redone.** `accounts.User.background_check_required`/`background_check_expires_at` (only ever set for `DojoOwner`/`HelperAccount`) back a `background_check_valid` property; `accounts.views.login` refuses a correct password once it's `False`, and `accounts.middleware.BackgroundCheckMiddleware` blocks every request from an already-logged-in session the same way, redirecting to `applications.views.renew_background_check` (same upload template as the emailed-link flow, `applications/templates/applications/upload_background_check.html`, just resolving the application from the authenticated account instead of a token). `Guardian`/`ChildAccount` never set these fields and never go through this pipeline at all.

### Dojo owner admin area

A dojo owner's admin screens (`/dojos/<id>/dashboard/` = attendance, `/dojos/<id>/manage/` = profile settings, `/dojos/<id>/events/` = events list, `/dojos/<id>/events/new/` = create an event, `/dojos/<id>/events/<event_id>/` = edit an event, more to come — Helpers & Mentors/Members are still stubbed nav links with no view yet) all extend `dojos/templates/dojos/_admin_base.html`, which owns the whole `<!doctype html>` shell (it doesn't extend `core/base.html` — this is an app-like admin surface with its own collapsible-sidebar layout via `CoderDojo.initAdminNav`, not a scrollable marketing page). The page scrolls naturally (no inner fixed-height/`overflow` scroll container) — `.cd-admin-nav`'s height comes from the shell's default flex `align-items: stretch` matching `.admin-main`'s natural content height, so the sidebar's background/border always run the full length of the page, however long that page is. Sidebar markup matches the CoderDojo design system's `AdminNav`/`AdminDashboard` components. A page extending it fills `admin_page_title`/`admin_heading`/`admin_content` (and optionally `admin_topbar_extra`, `admin_extra_style`/`admin_extra_script`) and passes an `active` context var (`"attendance"`, `"settings"`, `"events"`, ...) matching the sidebar link it should highlight. Every view here is `@login_required` and resolves its dojo through `dojos.views._get_owned_dojo` (404, not 403, on a mismatch — same reasoning as `accounts._get_own_guardian`) — **never `get_object_or_404(Dojo, ...)` alone** for an owner-facing admin view, or any other dojo owner can reach it by guessing an id.

`dojos.views.dojo_manage` (`DojoProfileForm`), the events screens below, and the notification bell (below) are the pieces of this wired to real data so far — Helpers & Mentors/Members are still stubbed links. `dojo_manage` covers everything shown on `dojo_detail.html` except `owner`/`location`/`province`, which aren't self-service: an address edit is re-geocoded on save (`geo.geocoding.geocode`, same tolerant-failure pattern as `dojos.search.resolve_search_origin` — a failed/no-match geocode never blocks the save) and a successful one also refreshes `province` via `geo.geocoding.find_province` (point-in-polygon against `geo.AdministrativeBoundary`, with a nearest-boundary fallback), so an owner never touches either field directly.

**Events**: `dojos.views.dojo_event_list`/`dojo_event_create`/`dojo_event_set_status` (views live in `dojos`, not `events`, matching the rest of this admin area — same as `dojo_dashboard` reaching directly into `events.Registration`) manage `events.Event` rows for one dojo. `Event.status` (`events/models.py`) is a three-state lifecycle — `draft` (model default; hidden from the public site via `EventQuerySet.visible()`, used by every public-facing query: `event_list`, `upcoming_available_events`, `dojo_detail`'s `next_event`, `dojos.search.attach_next_events`) → `open` (registrations open, `Event.registration_open`) → `closed` (registrations closed, gated in `events.views.event_signup`) — and only ever moves forward one step at a time, via the "Publish"/"Close registrations" actions on the events list (`dojo_event_set_status`, POST-only, each transition only valid from its specific source status). `events.forms.EventForm` (used by `dojo_event_create`) has three quirks worth knowing before touching it: (1) it takes a single `event_date` field plus separate `start_time`/`end_time` *time* fields (not two datetimes) — a session can't span midnight, and this makes that structurally true rather than validated; all three render in Belgian dd/mm/yyyy + 24h HH:MM notation regardless of the visitor's own browser locale (`EventForm.save()` combines them back into the model's real `start_time`/`end_time` datetimes). (2) Its banner `image` can come from an upload or from `template_image`, a picker over `events.template_images.TEMPLATE_IMAGES` (also the source seed data uses, see `seed_events.py`) — an uploaded file always wins if both are submitted. (3) `Event.mentors` is a `ManyToManyField` (not a single FK — a session can have more than one mentor), rendered as a checkbox list scoped to `dojo.mentors` in `EventForm.__init__`.

### Live notifications: Django Channels over Redis

The admin sidebar's notification bell (`dojos/templates/dojos/partials/_notification_bell.html`) is backed by `notifications.Notification` — `recipient` + `read` live on the same row, so per-user read state falls out for free; `dojo` (nullable FK) is what a multi-dojo owner's admin panel filters on, via `dojos.views._notification_context`. A dojo-level event that concerns more than one person fans out to one row per recipient sharing the same `dojo`/`text`/`url`, each independently read/unread.

**Creating a notification**: always through `notifications.services.notify(recipient, text, url="", dojo=None)` — never `Notification.objects.create()` directly. It creates the row (the source of truth) and then best-effort nudges that recipient's live connection via the channel layer; a channel-layer failure is swallowed, same fail-open spirit as `CACHES`' `IGNORE_EXCEPTIONS`. Two real call sites exist: `applications.views.register_helper` (a mentor application against a specific dojo notifies that dojo's owner) and `accounts.views.cancel_registration` (a waitlist promotion notifies the dojo's owner) — both skip silently if the dojo has no owner yet.

**Live push is WebSockets via Django Channels**, not SSE/polling — `daphne` (top of `INSTALLED_APPS`, so `manage.py runserver` transparently serves ASGI instead of WSGI), `ASGI_APPLICATION`/`CHANNEL_LAYERS` in `website/settings.py` (the latter is `channels_redis`, same `REDIS_HOST`/`REDIS_PORT` as `CACHES` but db 1, not 0), and `website/asgi.py`'s `ProtocolTypeRouter` (http → normal Django, websocket → `notifications.routing.websocket_urlpatterns` behind `AllowedHostsOriginValidator(AuthMiddlewareStack(...))`, so `scope["user"]` is the same session-authenticated user a normal request would see). `notifications.consumers.NotificationConsumer` checks dojo ownership once at `connect()` (closes the socket on a mismatch, same 404-not-403 reasoning as `dojos._get_owned_dojo`) and, on every group event, re-renders `_notification_bell.html` fresh from the DB and pushes it as one `hx-swap-oob="true"`-wrapped fragment — `htmx-ext-ws` (loaded in `_admin_base.html`) does the DOM swap from that alone, no client-side JSON handling. The bell's own `ws-connect` lives on a separate, never-swapped `<div>` in `_admin_base.html` specifically so the bell's own oob updates (and `mark_all_notifications_read`'s htmx response, which reuses the identical oob-id-matching trick) never tear down the socket that's delivering them.

If you add a Channels consumer that touches the database, test it with `TransactionTestCase`, not `TestCase` — the consumer's DB access runs on a separate thread (`channels.db.database_sync_to_async`) with its own connection, which a `TestCase`'s wrapping transaction (held on the main thread's connection) is invisible to. `notifications.tests`/`dojos.tests.NotificationConsumerTests` are the reference examples, including `@override_settings(CHANNEL_LAYERS=...InMemoryChannelLayer...)` so consumer tests don't need a real Redis.

`django-debug-toolbar`'s `CachePanel` and `TemplatesPanel` are disabled (`DEBUG_TOOLBAR_PANELS` in `website/settings.py`, dev-only either way) — both do unsafe lazy model stringification while serializing call/context args for display (cache-call args for `CachePanel`; every template context value, including `dojo.owner`, for `TemplatesPanel` — `DojoOwner.__str__` queries `self.dojos`), which is merely wasteful under WSGI but hard-errors every single page it touches (`SynchronousOnlyOperation`) now that requests are served over ASGI. Any other panel that stringifies arbitrary model instances is a candidate for the same bug if it starts erroring — these two are just the ones actually hit so far.

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
