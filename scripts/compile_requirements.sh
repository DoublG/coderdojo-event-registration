#!/usr/bin/env bash
# Writes every hash-checked requirements file from its source (.in), with the
# hashes of each package's files on PyPI (MAINTENANCE.md, "Hash-checked installs").
# Run it in the devcontainer after changing a .in file, and commit both:
#
#   scripts/compile_requirements.sh            # keep the versions, refresh hashes
#   scripts/compile_requirements.sh -P django  # also move django to its newest allowed version
#
# The .in files pin every version themselves, so a plain run changes no version.
# Order matters: the docs and CI-tool files are constrained to requirements-dev.txt.
# Dependabot reads each file's header for the options, so keep them on the command
# line (no --custom-compile-command).
set -euo pipefail
cd "$(dirname "$0")/.."

compile() {
    pip-compile --quiet --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url \
        "$@"
}

compile "${@}" --output-file=requirements.txt requirements.in
compile "${@}" --output-file=requirements-dev.txt requirements-dev.in
(cd docs && compile "${@}" --output-file=requirements.txt requirements.in)
(cd .github/requirements && compile "${@}" --output-file=ci-tools.txt ci-tools.in)
echo "Compiled: requirements.txt requirements-dev.txt docs/requirements.txt .github/requirements/ci-tools.txt"
