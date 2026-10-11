"""The Level27 deployment PDF, built from LEVEL27_DEPLOYMENT.md's prose (kept here, in the same
style as build_technical.py) plus screenshots of the Level27 panel in images/level27/.

Run from anywhere: python build_level27_deployment.py
"""

import base64
import html
import os

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "level27-deployment.pdf")
IMAGES = os.path.join(ROOT, "images", "level27")


def shot(name, caption="", rot=False):
    with open(os.path.join(IMAGES, f"{name}.jpg"), "rb") as f:
        data = base64.b64encode(f.read()).decode()
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    cls = "chart rot" if rot else "chart"
    return (
        f"<figure class='{cls}'><img src='data:image/jpeg;base64,{data}' alt='{html.escape(caption)}'>{cap}</figure>"
    )


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
figure.rot img { max-height: 165mm !important; width: 100%; object-fit: contain; }
h1 .n { color: #c94a23; margin-right: 2mm; }
h2 { font-size: 13pt; margin: 6mm 0 2mm; color: #111827; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 4mm 0 1.5mm; page-break-after: avoid; }
p { margin: 0 0 2.4mm; }
ul, ol { margin: 0 0 2.5mm; padding-left: 5mm; }
li { margin-bottom: 1mm; }
code { font-family: 'Cascadia Mono', Consolas, monospace; font-size: 8.6pt; background: #f3f4f6; padding: 0 1mm; border-radius: 1mm; }
pre { font-family: 'Cascadia Mono', Consolas, monospace; font-size: 8.2pt; background: #f3f4f6; padding: 2.5mm 3mm; border-radius: 1.5mm; overflow: hidden; white-space: pre-wrap; word-break: break-word; margin: 0 0 3mm; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 4mm; font-size: 9pt; page-break-inside: avoid; }
th { text-align: left; background: #f3f4f6; font-weight: 700; }
th, td { border-bottom: 0.3mm solid #e5e7eb; padding: 1.4mm 2mm; vertical-align: top; }
figure { margin: 3mm 0 5mm; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100% !important; max-height: 165mm; height: auto; border: 0.3mm solid #e5e7eb; border-radius: 1.5mm; }
figcaption { font-size: 8.5pt; color: #6b7280; margin-top: 1.5mm; }
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
    "What's provisioned",
    f"""
<p class='lede'>Production runs as one Level27 project (&ldquo;POC - Coderdojo Event System&rdquo;, project id
<code>22212</code>), package type <b>Run</b>, with <b>7 components</b> reached only through Level27's own
reverse proxy for one linked URL, <code>demo.coolestprojects.be</code>. There is no root access to the
underlying server: everything here is managed either through the Level27 panel, or over SSH as the
unprivileged account user <code>py10102</code>. This page is a snapshot of the panel on 11 October 2026 &mdash;
the panel is the source of truth, this a guided tour of it.</p>
{shot("project-status", "The project's own status page: project, component, running, limits, URL and SSL status all OK; the linked URL demo.coolestprojects.be with health, SSL and forced SSL green, caching off.")}
<h2>The 7 components</h2>
<table>
<tr><th>Group</th><th>Component</th><th>Type / image</th><th>Level27 id</th><th>Purpose</th></tr>
<tr><td>Applicatie</td><td><code>website</code></td><td>Python 3.14.7, uvicorn ASGI, <code>main:app</code></td><td><code>py10102</code></td><td>The Django app</td></tr>
<tr><td>Databank</td><td><code>mysql</code></td><td>MySQL 8.4</td><td><code>db03764</code></td><td>Production database</td></tr>
<tr><td>Databank</td><td><code>mysql-loadtest</code></td><td>MySQL 8.4</td><td><code>db05411</code></td><td>Disposable database for production load tests</td></tr>
<tr><td>Mail</td><td><code>mailpit</code></td><td><code>axllent/mailpit:latest</code></td><td><code>mp10263</code></td><td>Catches mail only during a load test or demo switch</td></tr>
<tr><td>Mail</td><td><code>mail</code></td><td>Level27's outbound relay</td><td><code>py10102</code></td><td>The real SMTP path production mail goes out through</td></tr>
<tr><td>Object cache</td><td><code>redis</code></td><td><code>redis:latest</code></td><td><code>rd12854</code></td><td>Cache (db 0), Channels (db 1) and Celery broker (db 2)</td></tr>
<tr><td>Optioneel component</td><td><code>celery</code></td><td>&ldquo;Worker&rdquo; type, two commands</td><td><code>py10102</code></td><td>Both Celery workers</td></tr>
</table>
<p>Extensie and Page cache groups are present but empty (0 components each) &mdash; by design: the site caches
<i>data</i> in Redis, never whole pages (<code>CLAUDE.md</code>, &ldquo;Caching&rdquo;), so there is
deliberately no Level27 page-cache component.</p>
{shot("components-overview-1", "Components tab, top half: Applicatie, Databank, Extensie, Mail.")}
{shot("components-overview-2", "Components tab, bottom half: Mail, Page cache, Object cache, Optioneel component, Certificaat.")}
<h2>Architectural choices the panel confirms</h2>
<ul>
<li><b>The database runs on its own dedicated host</b>, <code>agencyhosting-lesse-mysql8.level27.eu</code>
(internal IP <code>172.21.155.6</code>), separate from the web app's host,
<code>agencyhosting-lesse-web.level27.eu</code> (<code>194.32.155.7</code>).</li>
<li><b>The &ldquo;Mail&rdquo; app component and the &ldquo;website&rdquo; component share one Level27 app id</b>
(<code>py10102</code>): Level27's outbound relay is attached to the app, not a separate container &mdash;
matching <code>EMAIL_HOST=localhost</code> in production's <code>.env</code>.</li>
<li><b>Caching is off at the proxy</b> for the linked URL &mdash; intentional: every page carries its own CSP
nonce, CSRF token and per-account nav, so only the data behind it is cached, in the app's own Redis.</li>
<li><b>Forced SSL is on at the proxy</b>, independent of Django's own <code>SECURE_SSL_REDIRECT</code> (still
<code>false</code> pending confirmation Level27's proxy always sets <code>X-Forwarded-Proto</code>): the
proxy already refuses plain HTTP for this URL, ahead of whatever Django's own setting decides.</li>
<li><b>A second, disposable MySQL database</b> (<code>mysql-loadtest</code>) sits provisioned and idle most of
the time, used only for a production load test.</li>
</ul>
""",
)

# 2 -------------------------------------------------------------------------------------
section(
    "The components, one by one",
    f"""
<h2><code>website</code> (the Django app)</h2>
{shot("website-component", "The website component's own detail page: credentials, path, SSH keys, checks, connection info, activity log.")}
<ul>
<li><b>Credentials panel</b>: username <code>py10102</code>, password masked (Level27-managed).</li>
<li><b>Advanced panel</b>: path <code>/app</code>, Python <code>3.14.7</code>, ASGI server <code>uvicorn</code>,
command <code>main:app</code> &mdash; <code>main.py</code> re-exports <code>website.asgi.application</code> as
<code>app</code>, and gunicorn runs <code>gunicorn -k uvicorn.workers.UvicornWorker main:app</code>.</li>
<li><b>SSH keys</b>: one key registered, used by <code>scripts/deploy.sh</code>.</li>
<li><b>Checks</b>: HTTP, latency and SSL expiry against <code>demo.coolestprojects.be</code>, all green.</li>
<li><b>Connection info</b>: IPv4 <code>194.32.155.7</code>, IPv6 <code>2a02:5b41:4:440::4</code>, FQDN
<code>c40a7b15f.l27powered.eu</code>, HTTP/HTTPS 80/443, SSH/SFTP 22.</li>
<li><b>Activity log</b>: every panel change is attributed and timestamped &mdash; the authoritative record of
who changed what in the panel, alongside <code>MAINTENANCE.md</code>'s security log and the application's own
audit log.</li>
</ul>
<h2><code>mysql</code> and <code>mysql-loadtest</code></h2>
<p>Both MySQL 8.4, host wildcard (<code>%</code>), on the same dedicated database host. <code>mysql</code> is
the real production database; <code>mysql-loadtest</code> exists only so a load test can point the live app at
throwaway data without touching real families' bookings.</p>
<h2><code>mailpit</code> and <code>mail</code></h2>
<p><code>mail</code> (Level27's own relay) is what real production mail goes out through, all the time.
<code>mailpit</code> catches mail only when the app is deliberately pointed at it during a production load
test, so a test never sends real mail to real families.</p>
<h2><code>redis</code> (object cache)</h2>
<p>One Redis component serves three logically separate databases &mdash; <code>CACHES</code> (db 0), Channels
(db 1) and the Celery broker (db 2). Confirmed over SSH: Redis 8.10.1, <code>maxmemory</code> 512 MB, policy
<code>allkeys-lru</code>, not yet the <code>volatile-lru</code> the caching design assumes.</p>
<h2><code>celery</code> (the optional &ldquo;Worker&rdquo; component)</h2>
<p>One component, memory limit 512&nbsp;MiB, memory mode <b>kill</b>, running two separate commands &mdash; see
&ldquo;The two Celery workers on Level27&rdquo;.</p>
<h2>Certificate</h2>
<p>One certificate, <code>demo.coolestprojects.be</code>, issued via Let's Encrypt (auto-renewing), bound to
the website application.</p>
""",
)

# 3 -------------------------------------------------------------------------------------
section(
    "Networking, TLS and the domain",
    """
<ul>
<li>The public entry point is <code>demo.coolestprojects.be</code>, resolving to the web app's IPv4/IPv6 and
served, TLS included, by Level27's own reverse proxy &mdash; not anything in this repository. Apache serves
<code>/static/</code> and <code>/media/</code> directly from disk under the account's home directory, and
proxies everything else to the app's Unix socket, <code>/var/run/socket/py10102.socket</code>.</li>
<li>SSH is the only other path in: <code>py10102@c40a7b15f.l27powered.eu</code>, port 22, key-based only, no
root access.</li>
<li>The database host is separate from the web host on Level27's internal network.</li>
<li>Forced SSL is on for the linked URL; Django's own <code>SECURE_SSL_REDIRECT</code> is still off pending
confirmation Level27's proxy always sets <code>X-Forwarded-Proto</code> &mdash; the proxy's own forced-SSL
setting is a separate, already-active safety net ahead of that.</li>
<li>The proxy's maximum request body size, and how it connects to the app's socket (new connection per request,
or a kept-open pool), are both still unconfirmed with Level27.</li>
</ul>
""",
)

# 4 -------------------------------------------------------------------------------------
section(
    "The deploy procedure",
    f"""
<p class='lede'>Production is deployed with one script, <code>scripts/deploy.sh</code>
(<code>--check</code> for a read-only preflight). Both talk to the server only over the same SSH connection
the website component's registered key authorises.</p>
<ol>
<li><b>Bundles the working tree</b>, excluding development-only paths.</li>
<li><b>Installs <code>requirements.txt</code></b> into the exact pyenv environment gunicorn runs from
(<code>~/.pyenv/versions/py10102-3.14.7</code>) &mdash; not a separate <code>~/app/.venv</code>.</li>
<li><b>Runs <code>manage.py check</code> before touching the live app</b> &mdash; the main safety gate.</li>
<li><b>Rsyncs</b> the new code into <code>~/app</code>, keeping <code>.env</code>, <code>media/</code>,
<code>private_media/</code> and <code>staticfiles/</code> untouched.</li>
<li><b>Migrates</b> the database.</li>
<li><b>Runs <code>collectstatic</code></b> into <code>~/app/staticfiles</code>, which Apache serves at
<code>/static/</code>.</li>
<li><b>Puts the new code live</b>: a graceful <code>HUP</code> to gunicorn, or a systemd stop/start for daphne
(about 30 s down) &mdash; <code>deploy.sh</code> detects which is actually running.</li>
<li><b>Smoke-tests over the Unix socket</b> directly, bypassing the proxy.</li>
<li><b>Restarts both Celery workers with a warm shutdown</b>: <code>SIGTERM</code>, lets the in-flight task
finish, Level27's worker component restarts the process on the new code, then the script pings both.</li>
<li><b><code>chmod o+x "$HOME"</code> on every deploy</b> &mdash; guards against a concrete gotcha: switching
the app server in the panel resets the home directory to <code>750</code>, stripping the bit Apache needs to
traverse into <code>~/app/staticfiles</code>/<code>media</code>. Caused a real outage (every visitor 403 on
static/media for 7+ minutes) on 8 October 2026 when a panel-only change reset the permission outside of any
code deploy. <b>Not fully closed</b>: a panel change that isn't a code deploy still needs this run by hand.</li>
</ol>
{
        why(
            "Production env vars live only on the server, in ~/app/.env, never in this repository. manage.py check "
            "before touching the live app is what stops a broken migration or missing setting from ever reaching "
            "production, and the warm Celery shutdown is the only lever available since there's no systemd access "
            "to create units of our own on this account."
        )
    }
""",
)

# 5 -------------------------------------------------------------------------------------
section(
    "The two Celery workers on Level27",
    f"""
<p>Both workers run as one Level27 &ldquo;Optioneel component&rdquo; (type Worker) &mdash; the mechanism that
gives us two long-running background processes without systemd access: each worker is one line in the
component's command list, and Level27 restarts a command's process whenever it stops. Confirmed directly in
the panel, the two commands, in full:</p>
<h3>periodic (beat embedded, queue <code>periodic</code>)</h3>
<pre>cd /var/python/py10102/app && nice -n 10 celery -A website worker -n periodic@%h -Q periodic -c 1 -B \\
  --scheduler django_celery_beat.schedulers:DatabaseScheduler \\
  --max-tasks-per-child 100 --max-memory-per-child 160000 -l WARNING</pre>
<h3>mailing (default queue <code>celery</code>)</h3>
<pre>cd /var/python/py10102/app && nice -n 10 celery -A website worker -n mailing@%h -Q celery -c 1 \\
  --max-tasks-per-child 100 --max-memory-per-child 160000 -l INFO</pre>
<p>Both match the documented worker design (one queue each, concurrency 1, beat only on <code>periodic</code>)
with three production-only hardening flags not present in the devcontainer's version:</p>
<ul>
<li><b><code>nice -n 10</code></b> &mdash; lower CPU priority, since both workers share the machine with
gunicorn and Apache.</li>
<li><b><code>--max-tasks-per-child 100</code> and <code>--max-memory-per-child 160000</code></b> (156 MiB)
&mdash; each worker process is recycled after 100 tasks or once its child exceeds ~156 MB, on top of the
whole component's 512 MiB kill limit.</li>
<li><b><code>periodic</code> logs at <code>WARNING</code>, <code>mailing</code> at <code>INFO</code></b>
&mdash; the periodic worker's 10-second dispatcher would flood the log at <code>INFO</code>.</li>
</ul>
{
        why(
            "The component's 512 MiB ceiling is fixed by the Level27 package, not adjustable from the dashboard; "
            "what is a choice is its behaviour at the limit. Set to kill rather than throttle: a stress test with "
            "throttle caused a 19-minute mail stall, where kill recovered within seconds of a forced over-limit run."
        )
    }
""",
)

# 6 -------------------------------------------------------------------------------------
section(
    "Load testing in production",
    f"""
<p class='lede'>Two very different things both fall under &ldquo;load testing&rdquo; here, with very different
risk.</p>
<h2>Read-only checks &mdash; always safe</h2>
<ul>
<li><code>manage.py capacity_report</code> over SSH &mdash; database size and growth projection.</li>
<li><code>/metrics/</code> with <code>METRICS_TOKEN</code> &mdash; the site's own live counters.</li>
<li><code>scripts/deploy.sh --check</code> &mdash; whether the gunicorn concurrency cap is actually in effect.</li>
<li>A <code>public</code>-mode load test (<code>loadtest/run.sh ... public</code>) &mdash; visitors only, no
login, nothing written. Safe directly against the real production site.</li>
</ul>
<h2>A load test that logs in and books &mdash; needs the database switch</h2>
<p><code>loadtest/locustfile.py</code>'s <code>mixed</code> and <code>rush</code> modes log in and book real
sessions, so against the real production domain they would create fake bookings and send real mail. The
script refuses any host that isn't local unless <code>LOADTEST_CONFIRM_REMOTE_HOST</code> explicitly names
that exact host &mdash; a one-time, deliberate opt-in, never a default.</p>
<p>On a demo/showcase deployment that genuinely has no real users yet (confirmed with whoever owns the
decision each time, never assumed), <code>scripts/loadtest_demo.sh</code> and <code>scripts/run_demo.sh</code>
automate the only safe way to run these modes against the live domain: repoint the real, running app at the
disposable <code>mysql-loadtest</code> database for the test window, run the test, then put the real database
back &mdash; exactly what that component and <code>mailpit</code> are provisioned for.</p>
<h2><code>loadtest_demo.sh switch</code>, over SSH, never touching the local machine</h2>
<ol>
<li>Checks a mail-settings file for Mailpit exists on the server &mdash; <b>refuses without it</b>, since a
test database has made-up addresses.</li>
<li>Backs up <code>~/app/.env</code> &mdash; <b>refuses to overwrite an existing backup</b>, so
<code>restore</code> always has exactly one real <code>.env</code> to go back to.</li>
<li>Edits only the <code>DB_*</code> lines to point at <code>mysql-loadtest</code>'s credentials, and the mail
settings to Mailpit's; every other setting is untouched.</li>
<li>Reloads gunicorn (graceful <code>HUP</code>) and warm-restarts both Celery workers, confirming both answer
a ping.</li>
<li><b>Clears the Redis cache (db 0 only)</b> &mdash; the cache still holds the other database's content; on
8 October 2026 skipping this is exactly what let the real site briefly show test data after a restore.</li>
<li><b>Verifies, not just assumes</b>: reads <code>/metrics/</code> over the Unix socket directly and checks
the reported row counts actually match the throwaway database.</li>
</ol>
<p><code>run_demo.sh NAME USERS RATE DURATION [MODE]</code> then runs <code>loadtest/run.sh</code> against the
live domain with <code>LOADTEST_CONFIRM_REMOTE_HOST</code> set automatically to match &mdash; the one place
that confirmation is set non-interactively, only because <code>switch</code> already made it safe.
<code>restore</code> reverses all of it and removes the backup file, so a stale backup can never be mistaken
for &ldquo;still switched&rdquo;. <code>status</code> reports which database and mail server are currently
live, and whether a backup is present.</p>
<h2>A public load test against production, step by step</h2>
<ol>
<li>Pick a quiet moment and tell the board; check <code>/health/</code> first.</li>
<li>Make sure <code>METRICS_TOKEN</code> is set in production's <code>.env</code>.</li>
<li>Start small and stop at the first sign of trouble: 50 users for 3 minutes, then 150 (~30 req/s); don't go
past 300 without agreeing it with Level27 first.</li>
<li>Watch <code>/metrics/</code> while it runs; stop if p95 passes 2s, errors pass 1%, or <code>/health/</code>
goes to 503.</li>
<li>Compare against the devcontainer's own figures and keep the dated results file.</li>
</ol>
{
        why(
            "A production run goes through Level27's real proxy with real TLS, so it doubles as an end-to-end check "
            "of the proxy's own limits and connection behaviour towards gunicorn, not just the application's own cap."
        )
    }
""",
)

# 7 -------------------------------------------------------------------------------------
section(
    "Known constraints and gotchas",
    """
<p class='lede'>Things that only became visible once the app was actually run against Level27's real limits,
not the devcontainer's defaults.</p>
<ul>
<li><b>MySQL's real connection limit is much tighter than the devcontainer's default.</b> The app's DB user
has <code>max_user_connections = 32</code> (fixed by the hosting package), against the devcontainer's 151.
<code>gunicorn.conf.py</code>'s per-worker cap had to be lowered (25 &rarr; 8, 8 Oct 2026) once measured
against the real limit &mdash; the old value produced real <code>500</code> errors under a rush, not just
graceful <code>503</code> refusals.</li>
<li><b>The Celery component's 512 MiB limit is fixed by the package</b>; its behaviour at the limit (kill, not
throttle) is a choice that was made and tested.</li>
<li><b>Redis's eviction policy is <code>allkeys-lru</code>, not <code>volatile-lru</code>.</b> The caching
design assumes only timed keys (cache entries) are evicted under pressure; under <code>allkeys-lru</code> the
Celery broker's untimed queue and <code>/metrics/</code>'s counters are evictable too. Usage is tiny today, so
this is headroom, not an active incident.</li>
<li><b>A Level27 panel change that isn't a code deploy can silently break static/media serving</b> &mdash; the
<code>chmod o+x ~</code> gotcha (see &ldquo;The deploy procedure&rdquo;). The single highest-impact gap
documented here: it caused a real, if short, full-site outage already, purely from a panel setting change with
no code involved.</li>
<li><b>Several infrastructure questions are still open with Level27</b>: the proxy's maximum request body
size, whether it keeps connections open towards gunicorn, whether MySQL/Redis are dedicated or shared, who
rotates the Celery workers' log files, and who patches what.</li>
</ul>
""",
)


def html_doc():
    toc = "".join(f"<li>{t}</li>" for t, _ in SECTIONS)
    body = [
        "<div class='cover'><div class='brand'>CoderDojo Belgium · registration platform</div>"
        "<h1>Level27 deployment</h1>"
        "<div class='sub'>How production is provisioned on Level27, what each component does, how a deploy "
        "actually runs end to end, and how load is tested safely against the live site.</div>"
        f"<h2 style='margin-top:14mm'>Contents</h2><ol class='toc'>{toc}</ol>"
        "<div class='meta'>Generated from the repository and the Level27 panel, 11 October 2026 · "
        "user-journeys/scripts/build_level27_deployment.py · full prose in LEVEL27_DEPLOYMENT.md</div></div>"
    ]
    for i, (title, content) in enumerate(SECTIONS, 1):
        body.append(f"<h1 class='sec'><span class='n'>{i}</span>{title}</h1>{content}")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Level27 deployment</title>"
        f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>"
    )


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1000, "height": 1400})
        page.set_content(html_doc(), wait_until="load")
        page.pdf(
            path=OUT,
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template="<div style='font-size:7pt;color:#9ca3af;width:100%;padding:0 16mm;display:flex;"
            "justify-content:space-between'><span>CoderDojo Belgium · Level27 deployment</span>"
            "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>",
            margin={"top": "16mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
        )
        browser.close()
    print(OUT)


if __name__ == "__main__":
    main()
