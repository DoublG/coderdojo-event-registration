# Data model: API based management

Split out of `DATA_MODEL.md` §13 ("API based management") — the dojo API clients, OAuth 2.0 client credentials, scopes, and the event-sync plan for a champion planning a year from a spreadsheet. `DATA_MODEL.md` stays the index; it links here. Section number kept as in `DATA_MODEL.md` so existing "§13" references elsewhere in the repo still resolve.

---

## 13. API based management (in progress)

**Built: dojo API clients (OAuth 2.0 client credentials) and the attendance
API** (phases 1 and 4 below, without the check-in codes and organisation
clients); the rest is the plan. Three needs, from the original notes:

- **External registrations:** some events (CoderDojo Girlz, Coolest
  Projects: organisation events with `Event.external_registration_url`,
  §12) take their sign-ups on their own website. That site reports its
  registrations (registered, cancelled, waiting list) here, for the
  statistics.
- **Attendance:** an app (e.g. scanning children in at the door) marks who
  came, instead of the attendance list.
- **Event management:** a dojo creates its sessions, opens and closes them
  from its own tools.

django-ninja stays the framework (`/api/v1/`, OpenAPI reference at
`/api/v1/docs`); django-oauth-toolkit 3.4.1 is the OAuth 2.0 server.

### Decisions

1. **OAuth 2.0 client credentials (decided, built).** Safer than static
   API keys: the client secret only goes to the token endpoint, every
   other request carries a token that lasts an hour, a leaked token soon
   stops working, and it's the standard every language has libraries for.
   A client is a django-oauth-toolkit `Application` (confidential, client
   credentials grant only, secret stored hashed and shown once) linked to
   an `api.DojoApiClient`: its dojo, name, scopes and technical account.
   Later, a client may sign its token request with its own key
   (`private_key_jwt`) instead of a shared secret; check the toolkit's
   support first.
2. **Only the champion makes clients (decided, built):** a new capability
   `MANAGE_API`, champion only (not mentors): a client acts for the whole
   dojo. The dojo admin area's **API** page (`/dojos/<id>/manage/api/`):
   add (name + what it may do), new secret (the old one and its tokens
   stop working), delete (client, application and tokens deleted at once;
   its technical account switched off and kept for the history, so what
   it marked keeps its name). There's no separate "revoke": deleting is
   how a client is stopped (decided).
3. **Scopes (built: attendance):** `attendance:read` (the dojo's sessions,
   who has a confirmed place, the team) and `attendance:write` (mark who
   came). A client only gets the scopes its champion gave it
   (`api.scopes.ClientScopes`). Still to add with their phases:
   `events:read` and `events:write` (phase 3, below) and
   `external_registrations:write`. **Never** health notes, belts or
   badges, team or lifecycle changes: those stay with people.
4. **A technical account per client (decided, built):**
   `User.account_type = "service"`, unusable password: what
   `TeamAttendance.marked_by` and the audit log's actor point at. Never
   counted as a person: retention and account deletion skip it, segments
   only take adults.
5. **External registrants: no shadow users (recommended, not built).** The
   external site reports each registration with its own id and a status
   (`registered`, `waitlisted`, `cancelled`), without personal data
   (optionally age and gender for statistics, see open points), as
   `events.ExternalRegistration`, upserted. Shadow `User`/`Ninja` rows would
   put people who never signed up here in exports, retention and segments.
6. **Event management, designed for a champion planning a whole year at
   once from a spreadsheet, not just one session at a time (recommended,
   not built).** The concrete need: a dojo plans its year's sessions in
   Excel, then a macro on that sheet pushes the plan to the site over
   this API instead of the champion re-typing 40-odd sessions into the
   dojo's events screens by hand. Re-running the macro (the plan changed,
   or it's just run again) must update the same sessions, never duplicate
   them — the API has no natural key to recognise "the same session" by
   itself (dates and names repeat year to year), so the client supplies
   one:
   - **A new field, `Event.external_ref`** (free text, blank by default,
     unique together with `dojo`) — a stable key the spreadsheet itself
     generates once per row (e.g. a GUID, or just `"<season>-<week>"`)
     and reuses on every push. Not personal data (`accounts/privacy.py`
     equivalent: `register_not_personal`-style, same as the OAuth
     toolkit's own models); shown in `EventOut` so a client that lost its
     local mapping can still discover what's already synced.
   - **One endpoint does the upsert:** `POST /api/v1/events/sync` (scope
     `events:write`), body: a list of rows, each `external_ref` +
     `name`/`event_date`/`start_time`/`end_time`/`places`/`venue_name`/
     `min_age`/`max_age`/`audience`/`status` (the same fields as
     `EventForm`, minus `team`, `pathways`, `image` — see phase 3).
     `status` *is* a field here, unlike the human form: a bulk planning
     push reasonably wants to publish (or draft, or close) many sessions
     at once, with the same "any status to any other, no one-way
     lifecycle" rule `dojo_event_set_status` already applies — this is a
     deliberate difference from the UI form, not an inconsistency to
     resolve. A row whose `external_ref` already exists for this dojo
     updates that event; a new `external_ref` creates one (starting
     `draft` if `status` is omitted, same model default as everywhere
     else). Each row is validated and saved independently — one bad row
     (a past date, `min_age > max_age`, whatever `events/services.py`'s
     validation catches) never blocks the others — and the response
     lists every row's `external_ref`, the resulting `event_id`, and
     `created`/`updated`/`error` with a message. That shape is what
     makes a results column in the spreadsheet practical: the macro
     writes the response straight back next to each row it sent.
   - **Sync never deletes.** A row dropped from the sheet does nothing on
     its own — there's no "this disappeared, so delete it" semantics,
     because a fat-fingered spreadsheet edit deleting a session with real
     registrations is a worse failure mode than a stale draft session
     sitting unpublished. To retire a planned session, the sheet (or the
     champion by hand) sets that row's `status` back to `draft`, or
     leaves it `closed`; an actual delete, if ever wanted, stays a manual
     admin/UI action, never something a batch sync call does by itself.
   - **`events:read` and `events:write` are their own scopes, separate
     from `attendance:*`** (decision 3) — a planning-only client (just
     the spreadsheet macro) never needs attendance access, and an
     attendance scan app never needs to edit sessions. `GET /events`
     (today gated on `attendance:read` alone, since it predates this)
     should accept **either** `attendance:read` or `events:read`, so
     existing clients keep working unchanged while a new planning-only
     client can still list sessions without being handed attendance
     access it doesn't need.

### Phases

1. **Foundations** — *built for dojo clients:* `api` app, `DojoApiClient`,
   service accounts, the token endpoint (`/api/oauth/token/`, revoke at
   `/api/oauth/revoke/`), `api.auth.OAuth2` (401 without a valid
   token of an active client, 403 without the scope, 404 for another
   dojo's rows; described in the OpenAPI spec as an OAuth 2.0 client
   credentials scheme with each endpoint's scope), throttling per client
   (`API_RATE_LIMIT`), the audit log's
   actor, the champion's API page, privacy classification (the toolkit's
   models are not personal: client credentials only), and **a test that no
   API schema holds a field classified `special`, `criminal` or
   `security`, or anything `export=False`**. *Still to do:* organisation
   clients (for the organisation dojo's events, on the organisation
   dashboard).
2. **Shared services** — *built for attendance* (`events/attendance.py`,
   used by the dojo views and the API) and *for signing up and cancelling*
   (`events/registrations.py`, used by `event_signup` and
   `cancel_registration`; it locks the session's row, so the API's
   bookings will queue behind the site's). *Still to do:* event
   create/edit/status (`events/services.py`: `create_event`/
   `update_event`, the same validation `EventForm` does today — the
   date+time combination, `min_age <= max_age`, `places > 0` — called by
   both `dojos.views.event_pages` (replacing its direct `form.save()`)
   and the API, so the two never drift apart) before phases 3 and 5.
3. **Event management** (`events:read`/`events:write`, decision 6):
   `POST /api/v1/events/sync` (bulk upsert by `external_ref`, for a
   champion planning a year from a spreadsheet — the concrete driver for
   this phase) plus `GET /events` widened to accept either
   `attendance:read` or `events:read`. A single-row `POST /events`/
   `PUT /events/{id}` pair *could* be added alongside for a client that
   only ever manages one session at a time, but isn't required by the
   spreadsheet use case and can wait until something actually needs it.
   `team`, `pathways` and `image` stay out of the synced fields for now
   (open points) — set once in the dojo's own UI after a sync, not
   re-sent every year.
4. **Attendance** — *built:* `GET /api/v1/events?when=upcoming|past`,
   `GET /api/v1/events/{id}/attendance` (confirmed children and the team,
   each `attended` true / false / null), `PUT
   .../attendance/children/{registration_id}` and `PUT
   .../attendance/team/{membership_id}` (`{"attended": ...}`), `POST
   .../attendance/all-present`. Milestone badges follow as on the site; a
   milestone that grants a belt only gives the badge (a client never
   awards belts). *Still to do:* a **check-in code** per registration (a
   signed token as a QR code in the booking mail) for a scan app that
   doesn't need the list.
5. **External registrations** (`external_registrations:write`,
   organisation clients, events with `external_registration_url`).
6. **Apps used by a person (later, if needed):** the authorization code
   grant with PKCE, tokens tied to the person's own `User`, so every rule
   of `dojos.access` applies as on the site.
7. **Docs** — *built:* the help page for dojo teams
   (`docs/source/dojo-team/api-clients.rst`, en/fr/nl), the API section in
   `CLAUDE.md`; the OpenAPI page is the reference. *Still to do for phase
   3:* the actual audience for `/events/sync` is a non-technical dojo
   volunteer's Excel macro, not a developer reading the OpenAPI page —
   the help page needs a worked example (a suggested sheet layout: one
   column per field above, a results column) and a minimal VBA snippet
   (get a token from `/api/oauth/token/` with `WinHttpRequest`, `POST`
   the sheet's rows as JSON, write the response back per row), not just
   the schema reference.

### Open points

- Should the external site be able to send age and gender (decision 5), or
  only counts?
- Client secrets never expire today (renew them by hand); tokens last an
  hour. Should secrets expire, e.g. after a year?
- django-oauth-toolkit 3.4.1 officially supports Django up to 6.0; it runs
  our tests on 6.1. Watch its releases.
- **Production:** live and deployed — the MySQL client headers and GDAL/GEOS
  that used to block this are present (confirmed 8 Oct 2026, see
  `MAINTENANCE.md`); the API needs nothing more (same app server, under
  `/api/`).
- **For `/events/sync` (decision 6):** a cap on rows per call (50 covers a
  full year of weekly sessions with room to spare; proposing 200 so a
  twice-weekly dojo or a mid-year bulk correction doesn't need to split
  calls) — enforced the same way `EVENTS_LIMIT` already caps `GET
  /events`. Whether `team`/`pathways` belong in a later version of the
  sync payload once a client has a way to look membership/pathway ids up
  (a `GET /team` endpoint doesn't exist yet) — not needed for the first
  version. Whether `external_ref` should be visible/editable from the
  dojo's own UI (so a champion can tell which of their sessions came from
  a sync) or stay API-only.

