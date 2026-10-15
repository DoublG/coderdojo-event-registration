#!/usr/bin/env bash
# The version a deploy of HEAD gets (scripts/CLAUDE.md, "Versions"): CalVer,
# year.month.release-of-that-month in Belgian time, e.g. 2026.10.3. A commit
# that already has a CalVer tag (a deploy run again) keeps it. Needs the tags
# (actions/checkout with fetch-depth: 0).
#
# Prints, and appends to $GITHUB_OUTPUT when it's set:
#   version=2026.10.3   the version
#   new=true|false      whether the tag still has to be made after the deploy
#   previous=2026.10.2  the release before it, for the release notes (v1.0 before the first)
set -euo pipefail

CALVER='[0-9][0-9][0-9][0-9].*'
month="$(TZ=Europe/Brussels date +%Y.%-m)"

existing="$(git tag --points-at HEAD --list "$CALVER" | sort -V | tail -1)"
if [ -n "$existing" ]; then
    version="$existing" new=false
else
    # "2026.1.*" doesn't match 2026.10.x: the glob needs the dot after the month.
    last="$(git tag --list "$month.*" | sort -V | tail -1)"
    n="${last##*.}"
    version="$month.$(( ${n:-0} + 1 ))" new=true
fi
previous="$(git tag --list "$CALVER" | grep -vxF "$version" | sort -V | tail -1 || true)"
previous="${previous:-v1.0}"

printf 'version=%s\nnew=%s\nprevious=%s\n' "$version" "$new" "$previous" | tee -a "${GITHUB_OUTPUT:-/dev/null}"
