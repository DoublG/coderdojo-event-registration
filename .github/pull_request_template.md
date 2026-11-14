## What and why

<!-- What does this change, and why? Link the issue: "Fixes #123". -->

## How it was tested

<!-- The tests you added or ran; for a page, which role you checked it as. -->

## Checklist

Tick what applies; strike through or remove what doesn't.

- [ ] Tests for the new or changed behaviour, and `python manage.py test --debug-mode` passes in the devcontainer
- [ ] `ruff check .`, `ruff format --check .`, `lint-imports` and `mypy` pass
- [ ] Migrations included (`makemigrations --check` is clean)
- [ ] Texts translated in Dutch and French, `.po` and `.mo` committed
- [ ] Help centre (`docs/`) and its translations updated for a changed user-facing flow
- [ ] New fields or models classified in `privacy.py`, with an audit-log decision
- [ ] `check_a11y.py` passes after a markup or style change
- [ ] `check_journeys.py` run; stale persona PDFs regenerated or named here
- [ ] Dependency or image change: `MAINTENANCE.md` updated and `pip-audit` run
- [ ] `CLAUDE.md`, `DATA_MODEL.md` or other docs updated where they describe what changed
- [ ] No personal data in screenshots, logs or test data
