"""The technical foundation and data model PDF, built from DATA_MODEL.md and CLAUDE.md.

The diagrams are taken from DATA_MODEL.md as they are (found by a marker text in each
block), so the PDF follows the model when it changes; the prose here summarises both
files. Run from anywhere: python build_technical.py
"""

import base64
import html
import os
import re
import urllib.request

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
OUT = os.path.join(ROOT, "technical-foundation-and-data-model.pdf")
MERMAID = os.path.join(ROOT, ".shots", "mermaid-11.4.1.min.js")
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"

BLOCKS = re.findall(r"```mermaid\n(.*?)```", open(os.path.join(REPO, "DATA_MODEL.md")).read(), re.S)


def mm(marker, caption=""):
    """The first DATA_MODEL.md diagram containing `marker`."""
    for b in BLOCKS:
        if marker in b:
            cap = f"<figcaption>{caption}</figcaption>" if caption else ""
            return f"<figure><pre class='mermaid'>{html.escape(b)}</pre>{cap}</figure>"
    raise LookupError(f"No diagram with {marker!r} in DATA_MODEL.md")


CHARTS = os.path.join(REPO, "loadtest", "charts")
QUALITY_CHARTS = os.path.join(REPO, "quality", "charts")
IMAGES = os.path.join(ROOT, "images")  # screenshots for the documents (shot_error_page.py)


def chart(name, caption="", folder=CHARTS):
    """A chart from loadtest/charts.py (CAPACITY.md) or quality/charts.py
    (CODING_STANDARDS.md), embedded in the PDF."""
    with open(os.path.join(folder, f"{name}.png"), "rb") as png:
        data = base64.b64encode(png.read()).decode()
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f"<figure class='chart'><img src='data:image/png;base64,{data}' alt='{html.escape(caption)}'>{cap}</figure>"


def own(code, caption=""):
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f"<figure><pre class='mermaid'>{html.escape(code)}</pre>{cap}</figure>"


ARCHITECTURE = """flowchart TB
    B[Browser<br/>server-rendered HTML + htmx] -->|HTTPS, WSS| X[nginx / Level27 proxy<br/>TLS, /static, /media]
    X --> A[ASGI app<br/>gunicorn + uvicorn workers<br/>daphne in development]
    A --> DB[(MySQL<br/>GIS, the data,<br/>the mail queue)]
    A --> R0[(Redis db 0<br/>cache)]
    A --> R1[(Redis db 1<br/>Channels layer)]
    A -. enqueue .-> R2[(Redis db 2<br/>Celery broker)]
    R2 --> P[Celery 'periodic'<br/>beat embedded]
    R2 --> M[Celery 'mailing'<br/>default queue]
    P --> DB
    M --> DB
    M --> SMTP[SMTP server]
    P --> BOX[Bounce mailbox<br/>IMAP / POP3]
    APP[A dojo's app] -->|OAuth 2.0<br/>client credentials| A
"""

LAYERS = """flowchart TD
    V[Views, admin actions, API endpoints, Celery tasks] --> S
    subgraph S ["Services: the only place a rule is decided"]
        T[dojos.team] --- AC[dojos.access]
        AP[applications.services] --- AW[events.awards]
        MS[mailing.services.send] --- NT[notifications.services.notify]
        TS[accounts.two_step] --- CA[accounts.child_accounts]
        PR[privacy.erasure / export] --- EA[events.attendance]
    end
    S --> MO["Models and managers<br/>public(), visible(), of_guardian(), signable_by()"]
    MO --> DB[(MySQL)]
    S -. user-facing error .-> E["TeamError, OnboardingError, BeltError,<br/>CampaignError, TwoStepError, ..."]
"""

CSS = """
@page { size: A4; margin: 16mm 16mm 18mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', 'Nunito', Arial, sans-serif; color: #1f2937; font-size: 10.2pt; line-height: 1.5; margin: 0; }
.cover { height: 255mm; display: flex; flex-direction: column; page-break-after: always; }
.brand { color: #c94a23; font-weight: 800; letter-spacing: .05em; text-transform: uppercase; font-size: 9.5pt; }
.cover h1 { font-size: 30pt; line-height: 1.08; margin: 10mm 0 4mm; }
.cover .sub { font-size: 12.5pt; color: #4b5563; max-width: 150mm; }
.cover .meta { margin-top: auto; font-size: 9pt; color: #6b7280; }
h1 { font-size: 20pt; margin: 0 0 3mm; color: #111827; }
h1.sec { page-break-before: always; }
@page wide { size: A4 landscape; margin: 14mm 16mm 16mm; }
figure.rot { page: wide; margin: 0; }
figure.rot svg { max-height: 165mm !important; width: 100%; }
h1 .n { color: #c94a23; margin-right: 2mm; }
h2 { font-size: 13pt; margin: 6mm 0 2mm; color: #111827; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 4mm 0 1.5mm; page-break-after: avoid; }
p { margin: 0 0 2.4mm; }
ul { margin: 0 0 2.5mm; padding-left: 5mm; }
li { margin-bottom: 1mm; }
code { font-family: 'Cascadia Mono', Consolas, monospace; font-size: 8.6pt; background: #f3f4f6; padding: 0 1mm; border-radius: 1mm; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 4mm; font-size: 9pt; page-break-inside: avoid; }
th { text-align: left; background: #f3f4f6; font-weight: 700; }
th, td { border-bottom: 0.3mm solid #e5e7eb; padding: 1.4mm 2mm; vertical-align: top; }
figure { margin: 3mm 0 5mm; text-align: center; page-break-inside: avoid; }
figure svg { max-width: 100% !important; max-height: 200mm; height: auto; }
figcaption { font-size: 8.5pt; color: #6b7280; margin-top: 1.5mm; }
figure.chart img { width: 100%; max-height: 125mm; object-fit: contain; }
pre.mermaid { background: none; margin: 0; }
.why { background: #fff7ed; border-left: 1.2mm solid #c94a23; padding: 2.5mm 4mm; margin: 3mm 0 4mm; border-radius: 0 2mm 2mm 0; page-break-inside: avoid; }
.why b:first-child { color: #9a3412; }
.toc { columns: 2; column-gap: 10mm; font-size: 10pt; padding-left: 6mm; }
.toc li { margin-bottom: 1.2mm; }
.lede { font-size: 11pt; color: #374151; }
"""

SECTIONS = []


def section(title, body):
    SECTIONS.append((title, body))


def why(text):
    return f"<div class='why'><b>Why.</b> {text}</div>"


# 1 -------------------------------------------------------------------------------------
section(
    "What the site is",
    """
<p class='lede'>A Django site for CoderDojo Belgium: free coding clubs for children aged 7–17, run by
volunteers. It replaces spreadsheets and forms with one place where families find a dojo and sign
their children up, volunteers are vetted once and help at any dojo, dojo teams run their sessions,
and the organisation communicates, promotes and keeps the whole thing lawful.</p>
<table>
<tr><th>Who</th><th>What they do on the site</th></tr>
<tr><td>Visitors and families</td><td>Discover dojos and sessions, create a family account, sign children up (with a
waiting list), follow belts and badges, manage mail, security and their data.</td></tr>
<tr><td>Ninjas</td><td>Optionally their own login, given by a guardian: see their progress, sign themselves up.</td></tr>
<tr><td>Mentors</td><td>Apply once, pass a Belgian background check, then join any dojo's team: sessions,
attendance, belts and badges, the team.</td></tr>
<tr><td>Champions</td><td>Run a dojo: everything a mentor does plus its lifecycle, health notes, mail to the
families and API clients.</td></tr>
<tr><td>The organisation</td><td>Reviewers (background checks, applications), admins (campaigns, segments,
content, awards, privacy, people, security), the board; the Django admin only for technical fixes.</td></tr>
</table>
<h2>Where the knowledge lives</h2>
<ul>
<li><code>DATA_MODEL.md</code>: the data model, one Mermaid diagram per area, plus the design rationale and plan
of every larger change (sections 10–25). The diagrams in this document are taken from it unchanged.</li>
<li><code>CLAUDE.md</code>: the conventions, the architecture and the gotchas: what a developer (human or AI)
needs to change the code safely. Kept current in the same change as the code.</li>
<li><code>docs/</code>: the end-user help centre (Sphinx, English, French and Dutch).</li>
<li><code>user-journeys/</code>: one PDF per persona with screenshots, in English, Dutch and French.</li>
<li><code>CAPACITY.md</code>, <code>MONITORING.md</code>, <code>CODING_STANDARDS.md</code>, <code>MEMORY_PROFILE.md</code> and
<code>MAINTENANCE.md</code>: what was measured (load, growth, memory, every metric and dashboard panel), the standards
and their tooling, and the versions in use with their end-of-life dates and the security log.</li>
</ul>
<h2>In numbers</h2>
<table>
<tr><th>Django apps</th><td>15 of our own (plus <code>website</code> for settings)</td><th>Models</th><td>52 of our own</td></tr>
<tr><th>Test functions</th><td>about 1,150 (Django test runner)</td><th>Languages</th><td>English, Dutch, French</td></tr>
</table>
""",
)

# 2 -------------------------------------------------------------------------------------
section(
    "Technical foundation",
    f"""
<h2>The stack</h2>
<table>
<tr><th>Layer</th><th>Choice</th><th>Why</th></tr>
<tr><td>Language, framework</td><td>Python 3.14, Django 6.1</td><td>Batteries included (auth, admin, forms, i18n, migrations);
the admin doubles as the always-working emergency tool.</td></tr>
<tr><td>Database</td><td>MySQL 8.4 LTS with <code>django.contrib.gis</code></td><td>What the hosting offers; spatial columns for dojo
locations, postcodes and provinces.</td></tr>
<tr><td>Front end</td><td>Server-rendered templates + htmx 2.0 (served from our own static files), one hand-kept <code>bundle.js</code>/<code>bundle.css</code></td>
<td>No build step, no SPA: the server stays the single source of truth; htmx swaps fragments for the dynamic parts.</td></tr>
<tr><td>Serving</td><td>ASGI: gunicorn with uvicorn workers in production, daphne behind <code>runserver</code> in development</td>
<td>WebSockets for the live notification bell, in the same process as the pages.</td></tr>
<tr><td>Real time</td><td>Django Channels over Redis (db 1)</td><td>The bell updates itself without polling.</td></tr>
<tr><td>Background work</td><td>Celery 5.6, two workers, beat embedded in one; Redis db 2 as broker</td><td>Every mail, the nightly
engagement rebuild, retention and reminders run off the request.</td></tr>
<tr><td>Cache</td><td>Redis db 0 (<code>IGNORE_EXCEPTIONS</code>)</td><td>Public lists; the site keeps working if Redis hiccups.</td></tr>
<tr><td>Auth</td><td>django-two-factor-auth on django-otp, WebAuthn passkeys; login links</td><td>Optional two-step login for
everyone, enforceable per role by the organisation.</td></tr>
<tr><td>API</td><td>django-ninja + django-oauth-toolkit (client credentials)</td><td>Typed endpoints with an OpenAPI spec; apps act
for one dojo with scoped tokens.</td></tr>
<tr><td>Audit</td><td>django-auditlog</td><td>Who changed what, and who viewed the most sensitive data.</td></tr>
<tr><td>Hosting</td><td>Level27 Python hosting (SSH, systemd user units); a devcontainer for development</td><td>A small, affordable
setup for a volunteer organisation, deployed with one script.</td></tr>
</table>
<h2>How the pieces connect</h2>
{own(ARCHITECTURE, "Runtime architecture. Only nginx is exposed; in development it also serves the docs, Mailpit, phpMyAdmin and a test authenticator under their own paths.")}
<h2>Environments</h2>
<ul>
<li><b>Development</b> is the <code>.devcontainer</code> stack: nginx with a local CA for <code>coolregistration.localhost</code>
(only port 443 is published), MySQL, Redis, Mailpit catching every mail (and acting as the bounce mailbox), both
Celery workers, and seeded demo data from about twenty rerun-safe seed commands. Prometheus and Grafana (scraping
<code>/metrics/</code>, with a provisioned dashboard) come up behind a Compose profile when wanted. End-to-end checks go through nginx,
never straight to Django, because TLS, the WebSocket upgrade and the tool paths live there.</li>
<li><b>Production</b> is deployed by <code>scripts/deploy.sh</code>: bundle the tree, install requirements into the Python env
gunicorn uses, run <code>manage.py check</code> on the new code <i>before</i> touching the live app, rsync, migrate, reload
gunicorn, restart the Celery units and smoke-test. <code>--check</code> is a read-only preflight.</li>
<li><b>CI</b> (GitHub Actions) runs the checks, never a deploy: the whole test suite on every push and pull request
against MySQL 8.4 and Redis 7.2, a weekly and per-push code audit (<code>ruff</code> with its security rules, the import
layers, <code>pip-audit</code>, <code>check --deploy</code>, CodeQL), and the help centre published to GitHub Pages.</li>
</ul>
""",
)

# 3 -------------------------------------------------------------------------------------
section(
    "Architectural principles and their rationale",
    f"""
<p class='lede'>A handful of rules shape almost every part of the code. Each one exists because the alternative
went wrong, or would have, for a site that holds children's data and is maintained by volunteers.</p>
<h2>Rules live in services, views only call them</h2>
{
        own(
            LAYERS,
            "Every change with a rule behind it goes through one module, which raises an error with a user-facing message.",
        )
    }
{
        why(
            "One place decides each rule, so a view, an admin action, the API and a Celery job can never disagree. "
            "The API's attendance endpoints call the same <code>events.attendance</code> functions as the dojo's attendance list."
        )
    }
<h2>404, not 403, for what you may not see</h2>
<p>A dojo you are not on the team of, a child you are not a guardian of, an organisation page your role
doesn't open: all answer 404. A 403 is only for someone who <i>is</i> on the team but whose role lacks the capability.</p>
{why("A 403 confirms the thing exists. Guessable ids must not reveal which dojos, children or accounts are there.")}
<h2>Keep the history, never overwrite it</h2>
<ul>
<li>Team memberships go <code>dormant</code>, never deleted, so past sessions keep their team.</li>
<li>Belts (<code>NinjaBelt</code>), background-check decisions, consent (<code>ConsentEvent</code>) and cancellations
(<code>RegistrationCancellation</code>) are append-only logs.</li>
<li>A campaign freezes its segment at launch; a mail row stores exactly what was sent.</li>
</ul>
{why("Insurance, disputes and GDPR accountability all need to know what was true <i>then</i>, not what is true now.")}
<h2>Delete what you must not keep</h2>
<p>A criminal-record extract is deleted the moment a reviewer decides; only the decision stays. Private files have no URL
at all (<code>private_storage</code>, <code>base_url=None</code>), only a permission-checked download view.</p>
<h2>The Django admin always works</h2>
<p>Day-to-day work gets a page in a dashboard (the dojo area or the organisation area). The admin stays fully usable for
every model, never read-only, never with hidden fields, so that direct database access is never needed; a test checks
that a superuser can add, change and delete every registered model. The one exception is the audit log. Access to the
admin itself is time-boxed: an organisation role asks for it, 12 hours at a time.</p>
<h2>Server-driven UI</h2>
<p>htmx for anything that needs the server, plain HTML/CSS for pure client behaviour, hand-written JavaScript only for what
neither can do (passkeys, geolocation, scroll). Third-party browser code (htmx, OpenLayers, fonts) is served from our own
static files, never a CDN, so visitors' IP addresses don't go to a third party.</p>
<h2>Correctness traps turned into rules</h2>
<ul>
<li><b>Distances</b> always use <code>geo.functions.DistanceSphere</code> (MySQL <code>ST_Distance_Sphere</code>): Django's
<code>Distance()</code> silently returns planar degrees on MySQL.</li>
<li><b>A model's <code>__str__</code> never queries</b>: under ASGI a lazy lookup raises
<code>SynchronousOnlyOperation</code>; managers preload what <code>__str__</code> needs.</li>
<li><b>Cache data, never whole pages, and clear it on save</b>: every page carries its own CSP nonce, CSRF token and
nav, so the public content, the account's nav and the sessions are cached instead (<code>core/caching.py</code>), and
signals clear them whenever a row they're built from changes, so a published session shows at once. The account's nav
never decides access: the pages behind its links still ask the database.</li>
<li><b>A list counts in the same query</b>: <code>Event.objects.with_confirmed_count()</code> wherever the places left
show, instead of a query per row.</li>
<li><b>Tasks are safe to run twice</b> (<code>acks_late</code>, idempotency keys): a worker that dies mid-task is retried.</li>
</ul>
<h2>Enforced by tests</h2>
<p>Many of these are guarded by tests that fail on a new model or field that forgets them: every field has a privacy
classification, every model has an audit-log decision, every registered model is fully usable in the admin, every
<code>__str__</code> that follows a relation is preloaded, every form text is translated, the API schema never exposes a
sensitive field, no page loads a script from another site, and the public pages keep their query counts.</p>
""",
)

# 4 -------------------------------------------------------------------------------------
section(
    "The data model at a glance",
    f"""
<p class='lede'>Fifteen apps, in four layers, each with its own <code>urls.py</code> mounted at the top level. The diagrams
show the main entities and how they connect; the layers are below.</p>
{mm("subgraph accounts", "The main entities, grouped by the app that owns them (DATA_MODEL.md §1).")}
{mm("subgraph privacy", "Around the core: the apps that reach people and keep the record (DATA_MODEL.md §1).")}
<table>
<tr><th>App</th><th>Owns</th></tr>
<tr><td><code>accounts</code></td><td><code>User</code> (every login), <code>Ninja</code>, <code>Guardianship</code>, organisation roles, admin-access grants, invitations, the sign-in policy</td></tr>
<tr><td><code>dojos</code></td><td><code>Dojo</code> (with its lifecycle), <code>DojoMembership</code> (the team), access rules, geo-search</td></tr>
<tr><td><code>events</code></td><td><code>Event</code>, <code>Registration</code>, cancellations, badges, belts, team attendance, the engagement snapshot</td></tr>
<tr><td><code>applications</code></td><td><code>Application</code>, <code>BackgroundCheckHistory</code>, the background-check flow</td></tr>
<tr><td><code>pathways</code></td><td>The learning-track catalogue: pathways, steps, projects, skills</td></tr>
<tr><td><code>content</code></td><td>FAQs, testimonials, announcements, promotions, sponsors, the organisation's team listing</td></tr>
<tr><td><code>notifications</code></td><td>Per-recipient <code>Notification</code> rows behind the bells</td></tr>
<tr><td><code>mailing</code></td><td>The mail engine: every mail's queue, templates, preferences and consent, mutes, bounces, the automated mail</td></tr>
<tr><td><code>campaigns</code></td><td>Campaigns, segments, journeys and a dojo's own mail, on top of the engine</td></tr>
<tr><td><code>geo</code></td><td>Municipalities and administrative boundaries, geocoding, <code>DistanceSphere</code></td></tr>
<tr><td><code>privacy</code></td><td>The GDPR operations: the register, export, erasure, retention, erasure records</td></tr>
<tr><td><code>api</code></td><td>A dojo's API clients and the <code>/api/v1/</code> endpoints</td></tr>
<tr><td><code>core</code></td><td>The foundation: caching, uploads, the image library, the privacy registry, audit-log wiring, shared templates and static files</td></tr>
<tr><td><code>pages</code></td><td>The homepage, contact, <code>/manage/</code>'s landing, the audit log page, <code>/health/</code>, the Django admin site</td></tr>
<tr><td><code>monitoring</code></td><td>The site's measurements of itself: <code>/metrics/</code>, the daily capacity sample</td></tr>
</table>
<h2>Four layers</h2>
<table>
<tr><th>Layer</th><th>Apps</th></tr>
<tr><td>Top: the site as people meet it</td><td><code>pages</code></td></tr>
<tr><td>Across the domain</td><td><code>api</code>, <code>campaigns</code>, <code>privacy</code></td></tr>
<tr><td>The domain, with the mail engine and notifications</td><td><code>accounts</code>, <code>applications</code>, <code>content</code>, <code>dojos</code>, <code>events</code>, <code>mailing</code>, <code>notifications</code>, <code>pathways</code></td></tr>
<tr><td>Foundation: knows no app</td><td><code>core</code>, <code>geo</code>, <code>monitoring</code></td></tr>
</table>
<p>An app imports its own layer and the ones below, never one above; <code>lint-imports</code> (import-linter) checks it in
CI. When a lower layer needs something from a higher one, the higher one registers it at startup: the standard-image
folders, <code>/metrics/</code>' mail queue, which campaigns use a mail template.</p>
{
        why(
            "Before the split, core imported most apps and 24 pairs of apps imported each other, so any change could "
            "ripple anywhere. With the layers, the foundation and the mail engine can be changed without reading the "
            "apps on top, and the contract stops a new shortcut the day it's written."
        )
    }
<h2>Nomenclature</h2>
<p>The code and the UI use CoderDojo's own vocabulary:</p>
<table>
<tr><th>Term</th><th>Meaning</th><th>In the model</th></tr>
<tr><td><b>Champion</b></td><td>The dojo owner; exactly one per dojo</td><td>membership role <code>champion</code></td></tr>
<tr><td><b>Mentor / Coach</b></td><td>An adult helper</td><td>membership role <code>mentor</code></td></tr>
<tr><td><b>Ninja</b></td><td>A child aged 7–17 visiting a dojo</td><td><code>Ninja</code>, plus an optional ninja login (<code>User</code>)</td></tr>
<tr><td><b>Youth mentor</b></td><td>A ninja helping run sessions</td><td>membership role <code>youth_mentor</code> on a ninja login</td></tr>
<tr><td><b>Badge</b></td><td>An award: one-off, or a milestone reached by a count</td><td><code>Badge</code> (<code>one_off</code> / <code>milestone</code>), <code>NinjaBadge</code></td></tr>
<tr><td><b>Belt</b></td><td>A ninja's proficiency level</td><td><code>Belt</code>, the append-only <code>NinjaBelt</code> history</td></tr>
</table>
""",
)

# 5 -------------------------------------------------------------------------------------
section(
    "Accounts, families and roles",
    f"""
<p>One <code>User</code> table is every login, told apart by <code>account_type</code>: <code>adult</code>, <code>ninja</code> (a
child's own login) or <code>service</code> (an API client's technical account). There are no role subclasses.</p>
<ul>
<li><b>Parents</b> are plain adult accounts linked to children through <code>Guardianship</code> (a child can have several
guardians). No check, no approval: a parent only ever manages their own children.</li>
<li><b>A <code>Ninja</code> is not a user.</b> It gets a login only if a guardian gives it one; most never do. The guardian
creates and removes it and keeps editing the child's details.</li>
<li><b>Champions and mentors</b> are adult accounts with an approved <code>Application</code> and a valid background check;
what they do at a dojo is a <code>DojoMembership</code>.</li>
<li><b>Organisation roles</b> (<code>board</code>, <code>admin</code>, <code>reviewer</code>) map to permission groups kept in sync by
signals, and open areas of the organisation dashboard. The Django admin needs a separate, 12-hour grant.</li>
<li>Every login chooses a <b>password or an emailed login link</b>, with optional two-step login on top.</li>
</ul>
{mm("class Guardianship", "Accounts, guardianship and organisation access (DATA_MODEL.md §2).")}
{
        why(
            "Being a parent, a mentor or a champion describes how a person relates to children or to a dojo, not what kind of "
            "account they have, and one person can be all three. Modelling roles as subclasses spread one idea over several "
            "tables and needed sync code; relations make each role a row that can be added, ended and audited."
        )
    }
""",
)

# 6 -------------------------------------------------------------------------------------
section(
    "Dojos, teams and access",
    f"""
<p>A dojo's team is a set of <b>memberships</b>, one row per account and dojo, each with a role and a status.
The team-page profile (name, title, bio, photo) lives on the account and is shared by every dojo.</p>
{mm('DOJO ||--o{ DOJO_MEMBERSHIP : "memberships (team)"', "Dojos and their team memberships (DATA_MODEL.md §3).")}
<h2>Lifecycles</h2>
{
        mm(
            "created by an approved champion",
            "A dojo's status. Only active dojos (and their sessions) are public. Going dormant or archived needs no open sessions and declines pending join requests.",
        )
    }
{
        mm(
            "approved mentor asks to join",
            "A team membership. Leaving makes it dormant, never deleted, so past sessions keep their team.",
        )
    }
<h2>Who gets into a dojo's admin area</h2>
{mm("Active champion or mentor", "Access is always resolved through dojos.access.require_dojo_access.")}
<table>
<tr><th>Capability</th><th>Champion</th><th>Mentor</th></tr>
<tr><td>Dashboard, sessions list, the bell (any role)</td><td>✓</td><td>✓</td></tr>
<tr><td><code>TAKE_ATTENDANCE</code>, <code>MANAGE_EVENTS</code>, <code>EDIT_SETTINGS</code>, <code>MANAGE_TEAM</code></td><td>✓</td><td>✓</td></tr>
<tr><td><code>AWARD_BELTS</code>, <code>AWARD_BADGES</code>, <code>POST_UPDATES</code></td><td>✓</td><td>✓</td></tr>
<tr><td><code>MANAGE_LIFECYCLE</code>, <code>VIEW_HEALTH_NOTES</code>, <code>MANAGE_API</code>, <code>SEND_MAIL</code></td><td>✓</td><td>—</td></tr>
<tr><td>Hand over the champion role</td><td>✓</td><td>—</td></tr>
</table>
{
        why(
            "A lapsed background check never blocks login: the person can still use the site as a parent, but their memberships stop "
            "granting access until a renewal is validated. The membership keeps its status, so nothing needs repairing afterwards."
        )
    }
<p>Organisation-run events (CoderDojo Girlz, Coolest Projects) live on an <b>organisation dojo</b>
(<code>Dojo.kind = organisation</code>): a normal dojo with a team and an admin area, never listed publicly, and the only kind
whose events may link out to an external registration site.</p>
""",
)

# 7 -------------------------------------------------------------------------------------
section(
    "Sessions, registrations and attendance",
    f"""
{mm('EVENT }o--o{ DOJO_MEMBERSHIP : "team (M2M)"', "Events, registrations, pathways and the session's team (DATA_MODEL.md §4).")}
<ul>
<li><b>Places and the waiting list.</b> Places left = places − confirmed registrations. Cancelling deletes the registration
(after logging a <code>RegistrationCancellation</code>) and promotes the first child waiting; that family is mailed and the
dojo's team notified.</li>
<li><b>Attendance is tri-state</b> (<code>None</code> = not marked, present, absent), for children and for the session's team
(<code>TeamAttendance</code>, the record the insurance needs).</li>
<li><b>A girls' session</b> (<code>Event.audience</code>) is a label and a targeting signal, never a sign-up restriction.</li>
<li><b>Home dojo:</b> set at a child's first sign-up, then only the guardian changes it.</li>
</ul>
{mm("hidden from the public site", "A session's status is set directly by the team; it isn't one-way, and registrations are always kept.")}
<h2>Engagement</h2>
<p>Every night <code>events.engagement.rebuild()</code> recomputes, per child and dojo, how they come to sessions: new, regular,
occasional, at risk, lapsed, never came or aged out. Only sessions meant for the child count (age range, girls' sessions for
girls). Stage changes are logged, which lets a <i>journey</i> send a "we miss you" mail the week a child becomes at risk.</p>
{mm("NINJA_ENGAGEMENT_CHANGE", "Cancellations and the nightly engagement snapshot.")}
""",
)

# 8 -------------------------------------------------------------------------------------
section(
    "Badges and belts",
    f"""
<ul>
<li>A <b>badge</b> is an award. <i>One-off</i> badges are awarded by a dojo's team from the attendance list; <i>milestone</i>
badges (the attendance wristbands) are recomputed whenever attendance is marked and stay earned. Only the organisation
defines badges.</li>
<li>A <b>belt</b> is a ninja's proficiency level on one track, the only record of their coding level. The history is
append-only; the current belt is the highest. Only an active champion or mentor awards one, recording the account
<i>and</i> the membership (“Jan, as mentor of Dojo Ghent”). A milestone badge can grant a belt.</li>
</ul>
{mm("BELT |o--o{ BADGE", "Badges and belts; all rules in events/awards.py (DATA_MODEL.md §5).")}
{
        why(
            "Attendance and skill are different things: a child who comes every week isn't necessarily an advanced coder. "
            "Keeping milestones as badges and belts as a separate level lets both be shown honestly."
        )
    }
""",
)

# 9 -------------------------------------------------------------------------------------
section(
    "Volunteers: applications and background checks",
    f"""
<p>Belgian law (Art. 596.2) requires a criminal-record extract, model 2, for anyone working with minors. Onboarding is
<b>per account, once</b>: an approved mentor can join any number of dojos, an approved champion can create one.</p>
{
        mm(
            'USER ||--o{ APPLICATION : "applications"',
            "Applications and the append-only decision history (DATA_MODEL.md §6).",
        )
    }
{mm("reviewer requests it", "The background check lives on the account. Either decision deletes the document.")}
{mm("Adult account applies", "From application to a dojo.")}
{
        why(
            "A check is about a person, not about a dojo. Per-dojo applications made volunteers repeat the process and scattered "
            "the check across rows. Keeping only the decision (who, when, until when) and deleting the extract itself keeps the most "
            "sensitive document the site ever sees for the shortest possible time."
        )
    }
<p>Reviewers work on the organisation dashboard's <i>Volunteers</i> pages; nobody decides on their own check or application.
The account holder is reminded 30 days before expiry, and reviewers get a daily mail while documents wait.</p>
""",
)

# 10 ------------------------------------------------------------------------------------
section(
    "Pathways, content, notifications and geography",
    f"""
<h2>Pathways and content</h2>
<p>Pathways are a read-mostly catalogue, linked at three optional levels, each pre-filled from the one above but never
restricted to it: what a dojo provides → what a session covers → what one ninja works on.</p>
{mm('DOJO }o--o{ PATHWAY : "provides (M2M, optional)"', "Pathways and the content models; content is scoped to a dojo, event or pathway, or site-wide (DATA_MODEL.md §7).")}
<h2>Notifications</h2>
<p>One row per recipient, so read state is per person. <code>notify()</code> writes the row (the source of truth), then nudges
the recipient's open pages over the Channels layer; a failure there is swallowed. Texts are stored as translatable messages
and rendered in the <i>recipient's</i> language.</p>
{mm("participant C as NotificationConsumer", "A live notification: the consumer re-renders the bell and htmx swaps it in.")}
<h2>Geography</h2>
<p>Municipalities (postcodes with a centre) and administrative boundaries are reference data. A dojo's province is derived
from its geocoded location (point in polygon, nearest boundary as fallback). The dojo finder orders by
<code>DistanceSphere</code> from a typed address, the browser's location, the family's postcode or a Ghent default; only
the default list is cached, so one family's results never leak to another visitor.</p>
<p>A typed address becomes coordinates through <code>geo.geocoding.geocode</code>, the only way to call OpenStreetMap's
Nominatim, which allows one request a second for the whole site. It answers from the cache first (90 days for a match;
the key is a hash, so what someone typed isn't stored), then from our own municipalities for a postcode or a town's
name, and only then asks Nominatim, after taking a site-wide slot in Redis. When Nominatim asks us to slow down,
every call stops for a while; without Redis there's no call at all.</p>
""",
)

# 11 ------------------------------------------------------------------------------------
section(
    "The mail engine",
    f"""
<p>Every mail goes through one gateway, <code>mailing.services.send()</code>: it renders the template in the recipient's
language, checks consent and blocks, and inserts an <code>EmailMessage</code> row. <b>The database is the queue</b>; the
Celery workers only send.</p>
{mm("participant P as periodic worker", "How a mail goes out (DATA_MODEL.md §11).")}
{
        why(
            "A row per mail is the record of exactly what was sent, survives a broker restart, and makes retries and idempotency "
            "simple: a row is marked sent right after its own send, so a retry never mails anyone twice."
        )
    }
<table>
<tr><th>Worker</th><th>Runs</th><th>Why separate</th></tr>
<tr><td><code>periodic</code> (beat embedded)</td><td>The 10-second dispatcher, requeueing, bounces, the jobs beat triggers</td>
<td>The dispatcher never waits behind a big campaign; exactly one beat.</td></tr>
<tr><td><code>mailing</code> (default queue)</td><td>Batches of mail, campaign launches, everything else</td>
<td>With one process, Celery's rate limit is the real limit towards SMTP.</td></tr>
</table>
{mm("USER ||--o{ MAIL_PREFERENCE", "Consent and preferences, the queue, blocks and bounces.")}
<ul>
<li><b>Categories</b> (service, registration, reminder, dojo news, volunteer, newsletter) each with a default and whether
people may opt out; <code>ConsentEvent</code> logs every change with the privacy wording's version.</li>
<li><b>Segments</b> describe an audience without code: nested groups of rules about accounts or about “the same child”;
each rule is its own subquery. Child rules only reach guardians who consented.</li>
<li><b>Campaigns</b> freeze their segment at launch; <b>journeys</b> are standing campaigns run daily with a cool-down.</li>
<li><b>Bounces</b> are read from a mailbox (DSN, ARF): a hard bounce blocks the address, a complaint switches off optional mail.</li>
<li><b>A dojo's own mail</b> is a campaign with a dojo, sent by its champion to prepared audiences, with Reply-To the dojo.</li>
</ul>
{mm("SEGMENT ||--o{ SEGMENT_GROUP", "Campaigns, journeys and segments.")}
""",
)

# 12 ------------------------------------------------------------------------------------
section(
    "Security",
    f"""
<h2>Logging in</h2>
<p>There is one login page. A login link is the same login view with a different first step, so the second step always
follows. Passkeys are checked against the site's own URL, since TLS ends at the proxy.</p>
{mm("|no app or passkey|", "Password (or login link), then the second step when the account has one (DATA_MODEL.md §15).")}
<h2>The sign-in policy</h2>
<p>The organisation sets, per role and from a chosen date, the minimum: password, two-step login or passkey. An account's
requirement is the strongest among its roles. Today every role is on “password”; the enforcement is in place for when that
changes.</p>
{mm("Requirement today", "Enforcement: a middleware guides, and every door a role opens checks again.")}
<h2>Access to the management side</h2>
<ul>
<li>The organisation dashboard is split into <b>areas</b> (communication, public site, ninjas, privacy, security,
volunteers, audit log), each opened by a permission the roles grant.</li>
<li>The <b>Django admin</b> needs a grant asked for with a reason and the password, for 12 hours; the other admins are notified.
Superusers are only made on the server.</li>
<li>The <b>API</b> gives an app one dojo's data with scoped OAuth 2.0 tokens, through its own technical account, and is
tested never to expose a field classified as special, criminal or security data.</li>
</ul>
""",
)

# 13 ------------------------------------------------------------------------------------
section(
    "Privacy by design",
    """
<p>Most of the data is about <b>children</b>, one field is <b>health data</b> (allergies and notes, GDPR art. 9) and one flow
handles <b>criminal-record extracts</b> (art. 10). Privacy is therefore built into the model rather than bolted on.</p>
<h2>Every field is classified</h2>
<p>Each app declares its models in a <code>privacy.py</code>: purpose, legal basis, retention, who sees it, and for every
field whether it is personal (and in which category) and what happens to it on erasure: emptied, anonymised with a
replacement, or kept with a reason. A test fails on any unclassified field, ours or third-party. From that one registry:</p>
<ul>
<li><b>The register of processing activities</b> (<code>manage.py privacy_register</code>).</li>
<li><b>A person's export</b> (art. 15/20), for families from their account page and for the organisation on request.</li>
<li><b>Erasure</b>: rows are found by the registry's subjects, fields emptied or anonymised, <code>User</code> and
<code>Ninja</code> rows anonymised, never deleted, and an <code>ErasureRecord</code> without personal data allows replaying
erasures after a backup restore.</li>
<li><b>Retention</b>: an account is erased two years after its last login, after reminder mails; champions and mentors keep
their public team profile. A mail's subject, body and address are cleared 12 months after it was queued; the row stays
for the statistics.</li>
</ul>
<h2>The audit log</h2>
<p>django-auditlog records changes to the models listed in <code>core.audit.RECORDED</code> (every other model has a written
reason why not) and views of special-category data. Health notes and secrets are masked; IP addresses are never stored. It
is read-only, for the organisation's admins, and its entries follow the same retention and erasure.</p>
<h2>Who sees the most sensitive data</h2>
<table>
<tr><th>Data</th><th>Seen by</th><th>Safeguard</th></tr>
<tr><td>A child's health notes</td><td>The dojo's champion, only for children with a confirmed place</td><td>Every view recorded in the audit log</td></tr>
<tr><td>Criminal-record extract</td><td>Reviewers, until they decide</td><td>No URL; deleted on decision; downloads recorded</td></tr>
<tr><td>Families' addresses</td><td>Never the dojo team</td><td>Dojo mail shows counts only</td></tr>
</table>
""",
)

# 14 ------------------------------------------------------------------------------------
section(
    "Languages, testing and operations",
    """
<h2>Three languages, two kinds of text</h2>
<ul>
<li><b>The site's own texts</b> (templates, forms, messages, <code>bundle.js</code>) are in gettext catalogs for Dutch and French;
Dutch uses the informal “je”, French “vous”. The site language follows a cookie; an account's
<code>preferred_language</code> is only its mail language.</li>
<li><b>Content</b> written by people (a dojo's description, session names, updates, the organisation's pathways and
badges) is stored per language on the row, in the languages the dojo (or the organisation) chose; visitors see the main
language with an “Only in …” note when theirs is missing.</li>
<li>Mail templates are rows per language, falling back to English.</li>
</ul>
<h2>Testing</h2>
<ul>
<li>About 1,150 tests with the plain Django runner, inside the devcontainer, on their own Redis cache database.</li>
<li>Route tests check status codes, templates, permission gating (404 versus 403) and the database effect of a POST.</li>
<li>Channels consumers are tested with <code>TransactionTestCase</code> and an in-memory layer; Celery tasks by calling the
function, never <code>.delay()</code>.</li>
<li>The guard tests of chapter 3 keep new code honest about privacy, auditing, the admin, translations and the API schema.</li>
</ul>
<h2>Operations</h2>
<ul>
<li>One deploy script, with a preflight and a <code>manage.py check</code> before the live app is touched.</li>
<li><code>/health/</code> for an external uptime monitor (database, Redis, the mail workers), and <code>/metrics/</code>
(behind a token) for Prometheus: request and task timings, queues, table sizes and memory, never anyone's data.</li>
<li>Mail waits safely in the database when the workers are down; the dashboard's mail queue warns when due mail has waited
over 30 minutes.</li>
<li>Seed commands build a realistic demo world (dojos, families, volunteers, histories, waiting lists) and a credentials file
describing what each login can do; the user-journey PDFs are made from it.</li>
</ul>
<h2>Known gaps and open points</h2>
<ul>
<li>The API covers dojo clients and attendance; external registrations and event management are planned (§13).</li>
<li>Some privacy retention rules wait for their periods to be decided; their removals are built and stay off until then (§16).</li>
<li>Production still lacks MySQL client headers and GDAL/GEOS on the host; the deploy script refuses to go live until then.</li>
<li>Production's proxy still needs the 12 MB request-body limit the devcontainer's nginx has (chapter 15).</li>
</ul>
""",
)

# 15 ------------------------------------------------------------------------------------
section(
    "Capacity, load and disk",
    f"""
<p class='lede'>How big the database and the files get, what the site does under load, and how much memory each
component needs: measured on 30 September 2026 in the devcontainer, on a database filled with a year of the
<i>growth</i> scenario (100 dojos, 6,000 families, 1,200 sessions, 24,000 bookings and 189,000 mails a year). The
full report, with the method and how to measure again, is <code>CAPACITY.md</code>; the charts come from
<code>loadtest/charts.py</code>. The caching work was measured on 1 October 2026, the old and the new code with the same
runs.</p>
<h2>How it was measured</h2>
<ul>
<li><code>manage.py seed_scale</code> fills a separate <code>test_</code> database with a scenario's data, from rendered
mail to the engagement snapshot; <code>capacity_report --measure</code> stores the bytes each row takes.</li>
<li>A production-like run on it: <code>DEBUG</code> off, gunicorn with uvicorn workers and <code>gunicorn.conf.py</code>,
the two Celery workers with production's options, on Redis databases of their own.</li>
<li>Load from Locust (<code>loadtest/</code>): visitors, families that log in and book, dojo teams taking attendance,
and a registration rush; the site's own <code>/metrics/</code> sampled every 2 seconds.</li>
<li>Memory as PSS (each process's fair share of the memory forked processes share), never summed RSS.</li>
</ul>
{
        why(
            "The devcontainer isn't Level27's machine, so absolute response times will differ there. The memory figures and "
            "the comparisons between runs carry over; the public part of the test can be repeated on production itself."
        )
    }

<h2>Web workers set the response times</h2>
{chart("web-workers", "Mixed load; response times in ms.")}
<p>At the same load (300 users, about 63 requests a second) 4 web workers keep the 95th percentile at 110 ms where 2
let it climb to 610 ms. Logging in takes 250–350 ms: the password hash is slow on purpose.</p>

<h2>A registration rush</h2>
<p>Two problems showed up when 500 families signed up for the same five sessions at once. Both were fixed on
30 September 2026.</p>
<ul>
<li><b>Sessions overbooked</b> (up to 25 confirmed places on a session of 22, with duplicate waiting-list positions):
the sign-up read the places taken, then inserted, without a lock. Signing up and cancelling now go through
<code>events.registrations</code>, which locks the session's row first; real threads in
<code>BookingConcurrencyTests</code> fail without the lock.</li>
<li><b>MySQL ran out of connections</b>: under ASGI every request in progress holds its own connection, and uvicorn
starts any number of requests at once. <code>gunicorn.conf.py</code> now caps each worker at 25 connections
(uvicorn's <code>limit_concurrency</code>); beyond it the request gets an immediate 503.</li>
</ul>
{chart("rush-connections", "500 families, 4 web workers; MySQL connections sampled every 2 s.")}
{
        chart(
            "rush-outcomes",
            "Share of all requests. The same work gets done in each run (about 220 answered requests a second); what changes is how the rest fails.",
        )
    }
{chart("rush-latency", "95th-percentile response time of the answered requests.")}
{
        why(
            "A refused request costs nothing and can be retried; a request that waits for a database connection and then "
            "fails holds a worker, a thread and a connection while it waits, which slows everyone down."
        )
    }

<h2>Choosing the cap</h2>
{chart("cap-normal-load", "300 users, mixed load, 4 web workers.")}
<ul>
<li><b>25 refuses nothing under normal heavy load</b> and keeps a rush far from MySQL's limit; 10 already turns normal
traffic away. With 4 workers, at most about 100 connections plus Celery's.</li>
<li>uvicorn counts <b>open connections</b>, not requests: connections a proxy keeps open between requests, and open
notification WebSockets, take places too. How Level27's proxy connects to gunicorn is still to confirm.</li>
<li><code>scripts/deploy.sh --check</code> says whether gunicorn reads the file (it doesn't when it starts outside
<code>~/app</code> or with a <code>-c</code> of its own).</li>
<li><b>A refused visitor sees our own page</b>, not uvicorn's bare "Service Unavailable": the devcontainer's nginx serves
<code>errors/busy.html</code> (the site's design, Dutch, French and English, no script, trying again after 30 seconds)
for a 502, 503 or 504 from the site, keeping the status and adding <code>Retry-After</code>; <code>/health/</code> and the
API keep their own answers. It's the example for Level27's proxy.</li>
</ul>
{
        chart(
            "proxy-busy-page",
            "The proxy's busy page (errors/busy.html): desktop in light mode, a phone in dark mode.",
            IMAGES,
        )
    }

<h2>Caching: less work for the database</h2>
<p>The pages used to redo work the database had already done: a count query per session card, the account's roles and
dojos several times per request, the session row and the sign-in policy on every request, and site-wide content on every
visit. Since 1 October 2026 the lists count in the same query, sessions are read from Redis (and still written to
MySQL), the account's nav and the policy are cached, and so are the site-wide content, the events list's first page and
each dojo's page. A public page now makes 1 query instead of 8 to 24.</p>
{chart("caching-statements", "The same runs on the old and the new code: MySQL statements per answered request.")}
{chart("caching-latency", "Median and 95th percentile, before (grey) and after (blue).")}
<ul>
<li><b>A third fewer statements per request</b> (24.6 to 16.2). The rest is logged-in families booking, attendance marks
(writes) and 2 statements to open each request's own MySQL connection, which no cache saves.</li>
<li><b>Where the site was short of capacity, it shows</b>: with 2 web workers the 95th percentile halved (410 to 210 ms)
and the 0.8% of failed requests went away; in a rush, 17% more requests were answered in the same time.</li>
<li>Site-wide content is found in the cache 99.9% of the time; the events list's first page about 70%, because every
booking clears it so the places left stay right. Redis grew by 0.2 MB.</li>
</ul>
{
        why(
            "A cache that's cleared on every save shows a change at once; one that only expires would show a session "
            "as open for minutes after it filled up."
        )
    }

<h2>Memory</h2>
{chart("memory-under-load", "4 web workers, 300 users; PSS of all processes of each kind.")}
<table>
<tr><th>Component</th><th>Idle</th><th>Peak</th></tr>
<tr><td>Web: gunicorn master and 4 uvicorn workers</td><td>460 MB</td><td>750 MB (855 in an uncapped rush)</td></tr>
<tr><td>Celery periodic worker (parent, pool child, beat)</td><td>255 MB</td><td>255 MB</td></tr>
<tr><td>Celery mailing worker (parent, pool child)</td><td>160 MB</td><td>385 MB, nightly engagement rebuild</td></tr>
<tr><td>Redis (cache, Channels, broker)</td><td>3 MB</td><td>5 MB</td></tr>
<tr><td><b>Total</b></td><td><b>0.9 GB</b></td><td><b>about 1.45 GB: plan 2 GB</b></td></tr>
</table>
<p>The mailing worker's child reaches 300 MB during the nightly rebuild and is then replaced
(<code>--max-memory-per-child</code>, 200 MB); measured before 3 October 2026, when the rebuild's own peak went from
132 to 35 MB (section 16, "Memory per function"), so that peak should now be lower; a campaign launch stays at 160 MB because audiences are queued in chunks.
Mail goes out at 120 a minute by design: a campaign to 6,600 families takes about 55 minutes, with booking mail
ahead of it. Since 2 October 2026 a booking confirmation sent during a campaign waits about 16 seconds instead of two
minutes: the dispatcher keeps only two batches in flight (the broker sends first in, first out, so everything claimed
ahead was a wait), and a campaign is queued 200 accounts per task, each queueing the next behind what's waiting.</p>

<h2>Database growth</h2>
{chart("database-growth", "Projected size per scenario; dashed: mail text cleared after 12 months.")}
<ul>
<li>About 350 MB a year in the growth scenario, 1.6 GB after five years. 70% is the mail log: every mail keeps its
rendered text. Clearing it after 12 months, as the privacy register already says, saves about a quarter.</li>
<li>Accounts, children and bookings are anonymised, never deleted, so those tables only grow; the audit log is the
second-largest (525 bytes an entry).</li>
</ul>

<h2>Disk and uploads</h2>
<table>
<tr><th>On disk</th><th>Size</th></tr>
<tr><td>Database, binary logs, backups</td><td>1.6 GB after five years, plus tens of MB of logs and a copy per backup</td></tr>
<tr><td>Uploaded images (<code>media/</code>)</td><td>about 70 MB a year, made smaller when saved (0.8 GB as uploaded)</td></tr>
<tr><td>Standard images</td><td>a few MB: copied once, shared by every row that uses one</td></tr>
<tr><td>Code releases (5 kept), Python packages</td><td>7 MB a release, 236 MB</td></tr>
<tr><td>Celery's logs (journal)</td><td>small: the periodic worker logs at WARNING (at INFO it wrote about 6 MB a day)</td></tr>
</table>
<p>Teams upload dojo icons and session banners, the organisation promotion images, sponsor logos and badge icons,
volunteers their background-check document. Every upload goes through <code>core/uploads.py</code>:</p>
<ul>
<li><b>Limits</b>: an image at most 10 MB and 40 megapixels, a real raster image (never an SVG); the background-check
document at most 10 MB and a PDF, JPEG or PNG by its first bytes. The proxy refuses bodies over 12 MB.</li>
<li><b>Made smaller</b>: at most 1600 px (banners), 800 px (logos) or 512 px (icons, photos), re-encoded as JPEG, or PNG
with transparency.</li>
<li><b>No metadata survives</b>: the file is rebuilt from its pixels, so EXIF (a phone photo's GPS position), XMP,
comments, text chunks and colour profiles are left out, after the orientation and colour profile are applied.</li>
<li><b>Nothing left behind</b>: a replaced image, or one whose row is deleted, is deleted on commit, unless it's a
standard image or another row uses it.</li>
</ul>
{
        why(
            "Uploaded photos are public files: without this a banner kept the phone's GPS position of where it was taken, "
            "and a single photo could weigh more than a year of bookings."
        )
    }

<h2>Running it again, on production too</h2>
<ul>
<li>Read-only and safe on production: <code>manage.py capacity_report</code>, <code>/metrics/</code> with its token, the
daily <code>CapacitySample</code>, and <code>deploy.sh --check</code>.</li>
<li>A public load test (<code>loadtest/run.sh ... public</code>: visitors only, nothing written) at a quiet moment,
starting at 50 users; it goes through Level27's proxy, so it's also the end-to-end check.</li>
<li>The modes that log in and book refuse any host that isn't local: they'd book real sessions and mail real families.</li>
</ul>
""",
)


# 16 ------------------------------------------------------------------------------------
section(
    "Coding standards and quality",
    f"""
<p class='lede'>How code is written, checked and measured: the standards, the linting setup, the tests and what they
cover, how complex the code is and how much memory each function uses. Measured on 2 and 3 October 2026; the full
versions, with how to measure again, are <code>CODING_STANDARDS.md</code> and <code>MEMORY_PROFILE.md</code>, and the
conventions themselves are in <code>CLAUDE.md</code>.</p>

<h2>Production code and development-only code</h2>
<table>
<tr><th>Ships to production</th><th>Stays with developers</th></tr>
<tr><td>The apps and <code>website/</code>, <code>locale/</code>, <code>main.py</code>, <code>manage.py</code>,
<code>requirements.txt</code>, <code>gunicorn.conf.py</code>, the Celery systemd units</td>
<td><code>.devcontainer/</code>, <code>requirements-dev.txt</code>, <code>pyproject.toml</code>, <code>loadtest/</code>,
<code>quality/</code>, <code>user-journeys/</code>, <code>scripts/deploy.sh</code>, <code>.github/</code> (CI), <code>docs/</code>
(published to GitHub Pages)</td></tr>
<tr><td colspan='2'>In between: tests, seeders and import commands sit inside the apps and ship, but never run there
(the import commands' libraries aren't installed; <code>totp_code</code> and <code>simulate_bounce</code> need
<code>DEBUG</code>); the debug toolbar and django-silk only exist while <code>DEBUG</code> is on.</td></tr>
</table>

<h2>Standards and linting</h2>
<ul>
<li><b>Ruff</b>, pinned and configured in <code>pyproject.toml</code>: pycodestyle, pyflakes, import order, bugbear,
flake8-django and pyupgrade; the formatter decides the style (119 characters, double quotes). Security rules
(bandit) run separately; a reviewed line gets <code>noqa</code> with its reason.</li>
<li>The devcontainer's editor lints as you type and formats on save with the same Ruff.</li>
<li>CI: Ruff, the security rules, <code>pip-audit</code>, <code>manage.py check --deploy</code> and CodeQL in
<b>Code audit</b>; missing migrations and the whole suite in <b>Tests</b>.</li>
<li>Gated since 2 October 2026: no function over complexity 20 (Ruff <code>C901</code>, seed code excepted) and the
layers between the apps (<code>lint-imports</code>). Not gated, on purpose: types (no type checker) and a minimum
coverage. They're measured.</li>
</ul>

<h2>Tests</h2>
<p>1,132 tests (12,900 lines of test code for 25,000 lines of code). Routes are tested for status, template,
gating and the database effect of a POST; services with their refusals; concurrency with real threads. About
twenty <b>guard tests</b> fail on new code that forgets a rule: privacy classification, export coverage, an
audit-log decision, a usable admin, <code>__str__</code> without queries, translated form texts, security headers
and inline handlers, vendored scripts and fonts, the API schema. Every run shows a summary on GitHub and marks
failures on the failing line.</p>

<h2>Test coverage</h2>
{chart("coverage-per-app", "Statements and branches the tests run (coverage.py, branch coverage).", QUALITY_CHARTS)}
<table>
<tr><th>Covered well</th><th>Not covered</th></tr>
<tr><td>The business rules and their services (registrations, teams, awards, onboarding, mail, privacy, sign-in),
every page's gating, the API, monitoring, every guard rule: the site's own code at 94%, most apps at 91–99%.</td>
<td>Seeders and import commands (51%, development only); refusals of some rules (<code>dojos/team.py</code>,
<code>accounts/invitations.py</code>); two segment attributes; admin actions; outside-service failures; the ASGI
routing glue; one-line task wrappers.</td></tr>
</table>
{
        why(
            "Coverage is a map, not a target: it shows what no test runs, not whether a test checks the right thing. "
            "So it isn't gated in CI; the refusals of business rules are the gaps worth closing first."
        )
    }

<h2>Complexity</h2>
<p>An average complexity of 3.2; every module ranks A for maintainability. The site's six functions over 20 were
split on 2 October 2026 (the privacy registry's validation, the engagement rebuild and its metrics, the erasure's
collection, <code>event_signup</code>, <code>dojo_team_action</code>): only seed code is over 20 now, and Ruff fails any
new function that is. The three large views modules became packages by area.</p>
{chart("complexity-ranks", "Cyclomatic complexity of every function (radon).", QUALITY_CHARTS)}
{chart("most-complex", "The most complex functions; over 20 fails the lint, seed code excepted.", QUALITY_CHARTS)}

<h2>Memory per function</h2>
<p>Measured on 3 October 2026 by <code>quality/memory_profile.py</code>: every page (as the account that would open
it) and every background job, run once on a <code>seed_scale</code> database of a year's growth (8,962 children,
29,400 bookings, 188,926 mails) with production's settings. Python's <code>tracemalloc</code> counts the allocations
and <code>sys.monitoring</code> reports when each of the site's own functions starts and returns, so every function
gets its <b>peak</b> (the most memory a call needs, with what it calls), its <b>own peak</b> (without the site's
functions it calls: where to change it) and what it <b>keeps</b> after returning. Only Python's allocations count, so
processes are bigger (section 15); the figures show where memory goes and how it grows.</p>
<table>
<tr><th>Peak per call</th><th>Functions</th></tr>
<tr><td>up to 100 KB</td><td>643 of 747 (86%)</td></tr>
<tr><td>100 KB to 1 MB</td><td>82</td></tr>
<tr><td>1 to 10 MB</td><td>19</td></tr>
<tr><td>over 10 MB</td><td>3, all the nightly engagement rebuild</td></tr>
</table>
{chart("memory-steps", "Peak memory of the pages, writes and jobs that need the most (log scale).", QUALITY_CHARTS)}
<table>
<tr><th>Function</th><th>Peak</th><th>Verdict</th></tr>
<tr><td><code>events.engagement._registrations_by_ninja</code></td><td>128 MB, now 10.8 MB</td><td><b>Refactored
on 3 October 2026.</b> Each of the 29,400 bookings got its own copy of its session and dojo (<code>select_related</code>
over the whole table), so it grew with every booking. It now loads every session and dojo once and reads the
bookings as plain values, and the children's home dojos share the same dojos: the whole nightly rebuild went from
132 MB to 35 MB and from 12.6 to 7.4 seconds, writing the same 22,792 rows.</td></tr>
<tr><td>The attendance list's award forms (<code>dojos/forms.py</code>)</td><td>30 KB per form, now none</td><td><b>Fixed
on 3 October 2026.</b> A <code>lazy()</code> call per form built a new class each time, kept until the garbage
collector ran: 1.6 MB per page for 22 children, now 0.25 MB. <code>lazy()</code> is now called once at module
level (four other forms too), and a guard test fails on a <code>lazy()</code> call inside a function.</td></tr>
<tr><td>Pages</td><td>93 KB median, 2.7 MB at most</td><td>Fine: bounded by one session or one page of rows.</td></tr>
<tr><td>Mail jobs, campaign queuing, segments, export, retention</td><td>0.2–1.4 MB</td><td>Fine: they work in
chunks or let the database count, whatever the number of mails or accounts.</td></tr>
</table>
{
        why(
            "A job that reads a whole table should read values and share the small tables it refers to, never "
            "select_related across it: memory then grows with the small table, not the large one. Found on the way: "
            "the Mail queue page spent 6.6 seconds on one count over the mail log; an index on (status, sent_at) "
            "brought that count to a millisecond and the page to 0.3 seconds."
        )
    }

""",
)


def html_doc():
    toc = "".join(f"<li>{t}</li>" for t, _ in SECTIONS)
    body = [
        "<div class='cover'><div class='brand'>CoderDojo Belgium · registration platform</div>"
        "<h1>Technical foundation and data model</h1>"
        "<div class='sub'>How the site is built, how its data fits together, and why it looks the way it does. "
        "A summary of <code>DATA_MODEL.md</code> and <code>CLAUDE.md</code>, with the diagrams taken from the former.</div>"
        f"<h2 style='margin-top:14mm'>Contents</h2><ol class='toc'>{toc}</ol>"
        "<div class='meta'>Generated from the repository, 3 October 2026 · "
        "user-journeys/scripts/build_technical.py</div></div>"
    ]
    for i, (title, content) in enumerate(SECTIONS, 1):
        body.append(f"<h1 class='sec'><span class='n'>{i}</span>{title}</h1>{content}")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Technical foundation and data model</title>"
        f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    )


def main():
    if not os.path.exists(MERMAID):
        os.makedirs(os.path.dirname(MERMAID), exist_ok=True)
        urllib.request.urlretrieve(MERMAID_URL, MERMAID)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1000, "height": 1400})
        page.set_content(html_doc(), wait_until="load")
        page.add_script_tag(path=MERMAID)
        page.evaluate(
            """async () => {
                mermaid.initialize({startOnLoad: false, theme: 'neutral', securityLevel: 'loose',
                    fontFamily: 'Segoe UI, Arial, sans-serif', er: {useMaxWidth: true}, flowchart: {useMaxWidth: true}});
                await mermaid.run({querySelector: 'pre.mermaid', suppressErrors: true});
            }"""
        )
        rotated = page.evaluate(
            """() => {
                let n = 0;
                for (const svg of document.querySelectorAll('pre.mermaid svg')) {
                    const vb = svg.viewBox.baseVal;
                    if (vb && vb.width / vb.height > 1.5 && vb.width > 1100) {
                        svg.closest('figure').classList.add('rot');
                        n++;
                    }
                }
                return n;
            }"""
        )
        print("on landscape pages:", rotated)
        bad = page.evaluate(
            "() => [...document.querySelectorAll('pre.mermaid')].filter(p => !p.querySelector('svg') "
            "|| p.querySelector('.error-icon')).map(p => (p.parentElement.querySelector('figcaption') || {}).textContent)"
        )
        print("diagrams:", page.locator("pre.mermaid svg").count(), "failed:", bad)
        if bad:
            raise SystemExit("Some diagrams didn't render")
        page.pdf(
            path=OUT,
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template="<div style='font-size:7pt;color:#9ca3af;width:100%;padding:0 16mm;display:flex;"
            "justify-content:space-between'><span>CoderDojo Belgium · technical foundation and data model</span>"
            "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>",
            margin={"top": "16mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
        )
        browser.close()
    print(OUT)


if __name__ == "__main__":
    main()
