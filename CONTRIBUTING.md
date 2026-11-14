# Contributing

Thanks for helping CoderDojo Belgium. This site holds personal data about children, health notes and
volunteers' background checks, so changes are made carefully, with tests, and through a pull request.

- **Found a security problem?** Don't open an issue: see [`SECURITY.md`](SECURITY.md).
- **A bug or an idea?** Open an [issue](../../issues/new/choose) first for anything bigger than a small
  fix, so we can agree on the approach before you build it.
- Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## Setting up

Everything runs in the devcontainer: nginx with TLS, MySQL, Redis, Mailpit, the Celery workers and the
dev server, with seeded demo data. Open the folder in VS Code and *Reopen in Container*, or:

```sh
docker compose -f .devcontainer/docker-compose.yml up -d
docker compose -f .devcontainer/docker-compose.yml exec workspace bash
```

The site is then at `https://coolregistration.localhost/` and the seeded logins are in
`seed_credentials.csv`. More in the README's [Getting started](README.md#getting-started). Never run
`manage.py` against the host's Python or MySQL.

## Making a change

1. Branch from `main` (`fix/…`, `feature/…`).
2. Follow [`CODING_STANDARDS.md`](CODING_STANDARDS.md) and the conventions in [`CLAUDE.md`](CLAUDE.md)
   (it's written for AI agents, but it's the most complete description of how the code is organised and
   which rules hold: which module a change has to go through, the layers between the apps, privacy, i18n).
3. Add tests for every new view, model behaviour or non-trivial function, in the app's `tests.py`.
4. Run the checks inside the workspace container:

   ```sh
   python manage.py makemigrations --check
   python manage.py test --debug-mode
   ruff check . && ruff format --check .
   lint-imports
   mypy
   ```

5. Open a pull request against `main` and fill in its checklist. `main` is protected: every change,
   also the maintainers', goes in through a pull request (no force-push, no deleting the branch). The **Tests** and **Code audit** workflows
   run on it, and it can only be merged once they pass.

### What a change often needs as well

- **Translations:** every text a person sees is in English, Dutch (informal *je*) and French (*vous*):
  `makemessages`, translate, `compilemessages`, and commit both the `.po` and the `.mo` (CLAUDE.md, "i18n").
- **The help centre:** a change to a user-facing flow updates `docs/source/` and its Dutch and French
  translations ([`docs/README.md`](docs/README.md)).
- **Privacy:** a new field or model gets its GDPR classification in the app's `privacy.py`, and a decision
  about the audit log (CLAUDE.md, "Privacy" and "Audit log").
- **Accessibility:** after changing a page's markup or styles, run `user-journeys/scripts/check_a11y.py`
  (WCAG 2.2 AA).
- **User journeys:** `python3 user-journeys/scripts/check_journeys.py` says whether a persona's PDF needs
  a new version.
- **Dependencies and images:** a package goes in `requirements.in` (the site) or `requirements-dev.in`
  (development only), never in a `.txt` file: run `scripts/compile_requirements.sh`, which writes the
  `.txt` files with every package's hash, and commit both. A new or upgraded package or Docker image
  updates its row in [`MAINTENANCE.md`](MAINTENANCE.md); run `pip-audit -r requirements.txt`.
- **The data model:** update the diagram in [`DATA_MODEL.md`](DATA_MODEL.md).

### Optional: checks before every commit

[`.pre-commit-config.yaml`](.pre-commit-config.yaml) runs ruff and a few safety checks (no private keys,
no large files, no merge-conflict markers) on the files you commit. Install [pre-commit](https://pre-commit.com)
once where you run `git commit` (for example `pipx install pre-commit`) and then `pre-commit install`.

## Releases and deploying

`main` is where work comes together. The live site is deployed from the protected `demo` branch: a pull
request from `main` into `demo`, merged with a merge commit, runs the tests and deploys, and a successful
deploy is tagged with the next CalVer version (`2026.10.3`) and gets a
[GitHub Release](../../releases) with its notes. See [`scripts/CLAUDE.md`](scripts/CLAUDE.md).

## Licence

This repository is public but **not open source**: all rights are reserved ([`LICENSE`](LICENSE)). Whether
to publish it under an open-source licence will be decided later.

By opening a pull request you agree that your contribution is covered by the same terms, may be used in
this site, and may be published together with the rest of the project under an open-source licence if
that is decided later.
