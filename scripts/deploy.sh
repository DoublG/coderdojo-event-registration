#!/usr/bin/env bash
# Deploy this site to Level27 (Python hosting, SSH access).
#
# What it does:
#   1. Bundles the working tree (git-tracked + untracked-but-not-ignored
#      files, minus dev-only paths) into a tarball, with a BUILD_INFO file.
#   2. Uploads it (and, if present, a local production env file) to
#      ~/deploy/releases/<timestamp>/ on the server.
#   3. On the server, before touching the live app:
#        - installs requirements.txt into the Python env gunicorn runs from;
#        - runs `manage.py check` against the new code and the live .env.
#      A failure here aborts the deploy; the running site is untouched.
#   4. Syncs the release into ~/app (keeping .env, media/, private_media/ and
#      the demo logins in seed_credentials.csv),
#      runs migrations (+ collectstatic when STATIC_ROOT is configured).
#   5. Puts the new code live and does a smoke-test request over the app's
#      unix socket. Level27 runs the app as the systemd service py10102.service
#      with either gunicorn (HUP to its master: a graceful reload) or daphne
#      (the server chosen in the panel; it can't reload, so it's stopped and
#      systemd starts it again, Restart=always after 30 s: half a minute down).
#   6. Restarts the two Celery workers so they run the new code, and pings
#      them. Level27 runs them, not this script: the worker component "celery"
#      (Optioneel component in the panel) holds both commands and starts a
#      worker again whenever it stops, so a warm shutdown (SIGTERM: finish the
#      task in hand) is the restart. All mail goes through them, so a deploy
#      whose workers don't come back fails (DATA_MODEL.md §11, "Production:
#      two Celery workers as a Level27 worker component").
#
# Usage:
#   scripts/deploy.sh             # deploy (asks for confirmation)
#   scripts/deploy.sh --yes       # deploy without the confirmation prompt
#   scripts/deploy.sh --check     # read-only preflight: bundle + server checks, no changes
#
# Auth is SSH-key only (BatchMode): run it from the devcontainer (VS Code
# forwards your ssh-agent) or from the host.
#
# Settings (environment variables, all optional):
#   DEPLOY_REMOTE     ssh target            (default: py10102@c40a7b15f.l27powered.eu)
#   DEPLOY_ENV_FILE   local env file to install as ~/app/.env; skipped when the
#                     file doesn't exist, and the server's .env is kept as-is
#                     (default: .env.production; gitignored — never commit it)
#   DEPLOY_KEEP       releases to keep in ~/deploy/releases (default: 5)

set -euo pipefail

REMOTE="${DEPLOY_REMOTE:-py10102@c40a7b15f.l27powered.eu}"
ENV_FILE="${DEPLOY_ENV_FILE:-.env.production}"
KEEP="${DEPLOY_KEEP:-5}"

# Server layout (Level27): the app lives in ~/app, gunicorn runs from this
# pyenv virtualenv (NOT ~/app/.venv) and listens on this unix socket.
REMOTE_APP="app"
REMOTE_PY='$HOME/.pyenv/versions/py10102-3.14.7/bin/python'
REMOTE_SOCKET="/var/run/socket/py10102.socket"
# The systemd user units earlier deploys installed; removed when still there.
LEGACY_UNITS="coolregistration-celery-periodic coolregistration-celery-mailing"

# Never shipped: dev tooling and local-only material.
EXCLUDES_RE='^(\.devcontainer/|\.claude/|\.vscode/|\.github/|docs/|scripts/|user-journeys/|loadtest/|quality/|AGENTS\.md$|CLAUDE\.md$|DATA_MODEL\.md$|CAPACITY\.md$|CODING_STANDARDS\.md$|MEMORY_PROFILE\.md$|requirements-dev\.txt$|pyproject\.toml$|\.env\.example$)'

MODE="deploy"
ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        --check) MODE="check" ;;
        --yes|-y) ASSUME_YES=1 ;;
        -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
    esac
done

cd "$(git rev-parse --show-toplevel)"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE")
# Variable *names* only (never values) — used to warn about a .env missing keys.
EXAMPLE_KEYS="$(grep -oE '^[A-Z_][A-Z0-9_]*' .env.example 2>/dev/null | tr '\n' ' ')"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 0. preflight ----------------------------------------------------------
step "Preflight"
"${SSH[@]}" true 2>/dev/null || die "cannot ssh to $REMOTE (is your key loaded? try: ssh-add -l)"
echo "ssh: $REMOTE ok"

SHA="$(git rev-parse --short HEAD)"
DIRTY=""
if [ -n "$(git status --porcelain)" ]; then
    DIRTY="-dirty"
    echo "warning: working tree has uncommitted changes — they WILL be deployed:"
    git status --short | sed 's/^/    /'
fi
RELEASE="$(date +%Y%m%d-%H%M%S)-${SHA}${DIRTY}"
echo "release: $RELEASE"

if [ -f "$ENV_FILE" ]; then
    echo "env file: $ENV_FILE will be installed as ~/$REMOTE_APP/.env"
else
    echo "env file: $ENV_FILE not found — keeping the server's existing ~/$REMOTE_APP/.env"
fi

# --- 1. bundle ---------------------------------------------------------------
step "Bundling"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
BUNDLE="$WORK/release.tar.gz"
printf 'release=%s\ncommit=%s\nbuilt=%s\n' "$RELEASE" "$(git rev-parse HEAD)" "$(date -u +%FT%TZ)" > "$WORK/BUILD_INFO"

git ls-files -co --exclude-standard -z \
    | grep -zvE "$EXCLUDES_RE" \
    | while IFS= read -r -d '' f; do [ -e "$f" ] && printf '%s\0' "$f"; done \
    > "$WORK/files"
tar -czf "$BUNDLE" --null -T "$WORK/files" -C "$WORK" BUILD_INFO
echo "$(tr -cd '\0' < "$WORK/files" | wc -c) files, $(du -h "$BUNDLE" | cut -f1)"
for required in main.py manage.py requirements.txt website/asgi.py; do
    grep -qzx "$required" "$WORK/files" || die "bundle is missing $required"
done

# --- the remote side ----------------------------------------------------------
# One script, run over ssh with `bash -s`; MODE decides whether it only checks.
remote_script() {
cat <<REMOTE
set -euo pipefail
MODE="$MODE"; RELEASE="$RELEASE"; KEEP="$KEEP"; EXAMPLE_KEYS="$EXAMPLE_KEYS"
APP="\$HOME/$REMOTE_APP"; PY="$REMOTE_PY"; SOCKET="$REMOTE_SOCKET"; LEGACY_UNITS="$LEGACY_UNITS"
REL="\$HOME/deploy/releases/\$RELEASE"
step() { printf '\n\033[1m[server] %s\033[0m\n' "\$*"; }
die() { printf '\033[31m[server] error:\033[0m %s\n' "\$*" >&2; exit 1; }

# systemctl --user over a non-login ssh session needs the user's runtime dir.
[ -n "\${XDG_RUNTIME_DIR:-}" ] || [ ! -d "/run/user/\$(id -u)" ] || export XDG_RUNTIME_DIR="/run/user/\$(id -u)"

# The Celery workers' main processes (not their pool children): the ones the
# worker component's scripts (~/.worker/<id>) start.
celery_mains() {
    local pid parent
    for pid in \$(pgrep -u "\$USER" -f "celery -A website worker" || true); do
        parent="\$(ps -o ppid= -p "\$pid" | tr -d ' ')"
        tr '\\0' ' ' < "/proc/\$parent/cmdline" 2>/dev/null | grep -q "celery -A website worker" || echo "\$pid"
    done
}
celery_list() {
    local pid
    for pid in \$(celery_mains); do echo "worker \$pid: \$(tr '\\0' ' ' < "/proc/\$pid/cmdline" | cut -c1-160)"; done
}

# Earlier deploys ran the workers as systemd user units; next to the worker
# component they'd be a second beat (every job twice). Stop and remove them.
remove_legacy_units() {
    local unit found=""
    for unit in \$LEGACY_UNITS; do
        if [ -f "\$HOME/.config/systemd/user/\$unit.service" ]; then found="\$found \$unit"; fi
    done
    [ -n "\$found" ] || return 0
    systemctl --user disable --now \$found 2>/dev/null || true
    for unit in \$found; do rm -f "\$HOME/.config/systemd/user/\$unit.service"; done
    systemctl --user daemon-reload 2>/dev/null || true
    echo "removed the old systemd units:\$found"
}

# Both workers answer a ping. Right after a (re)start Celery still has to reach
# the broker, and Level27 has to start the worker again, so ask a while.
celery_ping() {
    local n
    for _ in \$(seq 1 18); do
        n="\$( cd "\$APP" && "\$PY" -m celery -A website inspect ping --timeout 10 2>/dev/null | grep -c ': OK' || true)"
        [ "\$n" -ge 2 ] && return 0
        sleep 5
    done
    return 1
}

missing_env_keys() {
    local k missing=""
    for k in \$EXAMPLE_KEYS; do grep -qE "^\$k=" "\$APP/.env" 2>/dev/null || missing="\$missing \$k"; done
    echo "\$missing"
}

daphne_pid() { pgrep -u "\$USER" -o -f "daphne.*\$SOCKET" || true; }

# Which server Level27 runs (the panel's choice). gunicorn.conf.py (the
# concurrency cap per web worker, CAPACITY.md) only counts when gunicorn starts
# in \$APP without a -c of its own: say whether it does. daphne has no such cap.
app_server() {
    local master args cwd pid
    master="\$(pgrep -u "\$USER" -o -f "gunicorn.*\$SOCKET" || true)"
    if [ -z "\$master" ]; then
        pid="\$(daphne_pid)"
        if [ -n "\$pid" ]; then
            echo "daphne: \$(tr '\\0' ' ' < "/proc/\$pid/cmdline")"
            echo "gunicorn.conf.py: not used (daphne): no concurrency cap per worker"
        else
            echo "app server: neither gunicorn nor daphne is running on \$SOCKET"
        fi
        return
    fi
    args="\$(tr '\\0' ' ' < "/proc/\$master/cmdline")"
    cwd="\$(readlink "/proc/\$master/cwd")"
    echo "gunicorn: \$args (in \$cwd)"
    if echo "\$args" | grep -qE -- ' (-c|--config)[ =]'; then
        echo "gunicorn.conf.py: IGNORED, gunicorn is started with a config of its own: the concurrency cap is off"
    elif [ "\$cwd" = "\$APP" ] && [ -f "\$APP/gunicorn.conf.py" ]; then
        echo "gunicorn.conf.py: read (concurrency cap \${UVICORN_LIMIT_CONCURRENCY:-25} per worker, from gunicorn's next start or reload)"
    else
        echo "gunicorn.conf.py: NOT read, gunicorn doesn't start in \$APP: the concurrency cap is off"
    fi
}

step "Checking server layout"
[ -x "\$PY" ] || die "python env not found: \$PY"
[ -d "\$APP" ] || die "app folder not found: \$APP"
echo "python: \$("\$PY" --version)"

if [ "\$MODE" = check ]; then
    if [ -f "\$APP/.env" ]; then
        M="\$(missing_env_keys)"; echo ".env: present\${M:+, missing keys from .env.example:\$M}"
    else
        echo ".env: MISSING"
    fi
    step "App server"
    app_server
    step "Celery workers"
    celery_list
    [ "\$(celery_mains | wc -l)" -eq 2 ] || echo "celery: expected 2 workers, check the worker component \"celery\" in the Level27 panel and ~/logs/worker-*/"
    for unit in \$LEGACY_UNITS; do
        if [ -f "\$HOME/.config/systemd/user/\$unit.service" ]; then
            echo "\$unit: old systemd unit still installed (\$(systemctl --user is-active "\$unit" 2>/dev/null || true)), the next deploy removes it"
        fi
    done
    step "Would-be requirements install (dry run)"
    "\$PY" -m pip install --dry-run --quiet -r /dev/stdin < "\$HOME/deploy/check-requirements.txt" \
        && echo "requirements: installable" || echo "requirements: NOT installable (see above)"
    rm -f "\$HOME/deploy/check-requirements.txt"
    exit 0
fi

step "Unpacking release"
mkdir -p "\$REL"
tar -xzf "\$HOME/deploy/incoming.tar.gz" -C "\$REL"
rm -f "\$HOME/deploy/incoming.tar.gz"
if [ -f "\$HOME/deploy/incoming.env" ]; then
    install -m 600 "\$HOME/deploy/incoming.env" "\$APP/.env"
    rm -f "\$HOME/deploy/incoming.env"
    echo ".env: installed from upload"
fi
[ -f "\$APP/.env" ] || die "no \$APP/.env on the server and none uploaded"
chmod 600 "\$APP/.env"
M="\$(missing_env_keys)"; [ -z "\$M" ] || echo "warning: .env lacks keys listed in .env.example:\$M"

step "Installing requirements"
"\$PY" -m pip install --quiet --upgrade pip
"\$PY" -m pip install --quiet -r "\$REL/requirements.txt"

step "Checking the new code before going live"
ln -sfn "\$APP/.env" "\$REL/.env"
( cd "\$REL" && "\$PY" manage.py check ) || die "manage.py check failed — the live site was NOT changed"
( cd "\$REL" && "\$PY" -c "import main" ) || die "main:app does not import — the live site was NOT changed"
# Production's security settings (https, HSTS, cookies): reported, never blocking.
( cd "\$REL" && "\$PY" manage.py check --deploy --fail-level ERROR 2>&1 | grep -E "^\\?: \\(security|identified" ) || true
rm -f "\$REL/.env"

step "Syncing into \$APP"
rsync -a --delete \
    --exclude='.env' --exclude='media/' --exclude='private_media/' \
    --exclude='staticfiles/' --exclude='.venv/' --exclude='.git/' \
    --exclude='__pycache__/' --exclude='seed_credentials.csv' \
    "\$REL/" "\$APP/"

step "Migrating"
cd "\$APP"
"\$PY" manage.py migrate --noinput
# Automated mail needs its templates: creates missing ones, never overwrites.
"\$PY" manage.py load_mail_templates
if "\$PY" manage.py shell -c "from django.conf import settings; import sys; sys.exit(0 if getattr(settings, 'STATIC_ROOT', None) else 1)" 2>/dev/null; then
    "\$PY" manage.py collectstatic --noinput --verbosity 0 && echo "collectstatic: done"
else
    echo "collectstatic: skipped (STATIC_ROOT not set)"
fi

step "Putting the new code live"
MASTER="\$(pgrep -u "\$USER" -o -f "gunicorn.*\$SOCKET" || true)"
OLD_DAPHNE="\$(daphne_pid)"
if [ -n "\$MASTER" ]; then
    kill -HUP "\$MASTER"
    sleep 5
    kill -0 "\$MASTER" 2>/dev/null || die "gunicorn master \$MASTER died after reload"
    echo "gunicorn master \$MASTER reloaded, \$(pgrep -u "\$USER" -P "\$MASTER" | wc -l) worker(s) up"
elif [ -n "\$OLD_DAPHNE" ]; then
    # daphne can't reload: stop it, and systemd (Restart=always) starts it on the new code.
    kill -TERM "\$OLD_DAPHNE"
    echo "daphne \$OLD_DAPHNE stopped; waiting for systemd to start it again (about 30 s)"
    NEW=""
    for _ in \$(seq 1 90); do
        NEW="\$(daphne_pid)"
        [ -n "\$NEW" ] && [ "\$NEW" != "\$OLD_DAPHNE" ] && break
        NEW=""
        sleep 1
    done
    [ -n "\$NEW" ] || die "daphne didn't come back within 90 s: restart the app from the Level27 panel"
    sleep 3
    echo "daphne \$NEW running the new code"
else
    die "neither gunicorn nor daphne found on \$SOCKET (is the app running? restart it from the Level27 panel)"
fi
app_server

step "Smoke test"
HOST="\$(grep -E '^ALLOWED_HOSTS=' "\$APP/.env" | cut -d= -f2 | tr ',' '\n' | grep -vE '^(localhost|127\.0\.0\.1|)\$' | head -1)"
CODE="\$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 --unix-socket "\$SOCKET" -H "Host: \${HOST:-localhost}" -H 'X-Forwarded-Proto: https' "http://\${HOST:-localhost}/")"
echo "GET / (Host: \${HOST:-localhost}) -> \$CODE"
case "\$CODE" in 2??|3??) ;; *) die "smoke test failed (HTTP \$CODE) — check ~/logs and 'manage.py check --deploy'";; esac

step "Celery workers"
remove_legacy_units
# A restart, not a reload: a worker keeps running the code it started with.
# SIGTERM is Celery's warm shutdown; the worker component starts it again.
OLD_WORKERS="\$(celery_mains | tr '\\n' ' ')"
[ -n "\$OLD_WORKERS" ] || die "the site is live, but no Celery worker runs: check the worker component \"celery\" in the Level27 panel and ~/logs/worker-*/"
kill -TERM \$OLD_WORKERS
for _ in \$(seq 1 130); do
    alive=""
    for pid in \$OLD_WORKERS; do if kill -0 "\$pid" 2>/dev/null; then alive="\$alive \$pid"; fi; done
    if [ -z "\$alive" ]; then break; fi
    sleep 1
done
[ -z "\$alive" ] || die "the site is live, but Celery worker(s)\$alive didn't stop within 130 s"
echo "workers \$OLD_WORKERS stopped (warm shutdown); waiting for Level27 to start them again"
if celery_ping; then
    celery_list
    echo "celery: both workers answer"
else
    die "the site is live, but the Celery workers don't answer a ping: check ~/logs/worker-*/worker-command*.log"
fi

step "Cleaning old releases (keeping \$KEEP)"
ls -1dt "\$HOME/deploy/releases"/*/ 2>/dev/null | tail -n +\$((KEEP + 1)) | xargs -r rm -rf
echo "deployed \$RELEASE"
REMOTE
}

# --- 2/3. check mode: read-only ------------------------------------------------
if [ "$MODE" = check ]; then
    step "Server checks (read-only)"
    "${SSH[@]}" 'mkdir -p ~/deploy && cat > ~/deploy/check-requirements.txt' < requirements.txt
    remote_script | "${SSH[@]}" bash -s
    step "Check finished — nothing was changed on the server"
    exit 0
fi

# --- 2. confirm + upload -------------------------------------------------------------
if [ "$ASSUME_YES" -ne 1 ]; then
    printf '\nDeploy %s to %s:~/%s? [y/N] ' "$RELEASE" "$REMOTE" "$REMOTE_APP"
    read -r answer
    [[ "$answer" =~ ^[Yy]$ ]] || die "aborted"
fi

step "Uploading"
"${SSH[@]}" 'mkdir -p ~/deploy/releases'
scp -q -o BatchMode=yes "$BUNDLE" "$REMOTE:deploy/incoming.tar.gz"
if [ -f "$ENV_FILE" ]; then
    scp -q -o BatchMode=yes "$ENV_FILE" "$REMOTE:deploy/incoming.env"
fi

# --- 3-5. install, verify, go live -------------------------------------------------
remote_script | "${SSH[@]}" bash -s
step "Done: $RELEASE is live"
