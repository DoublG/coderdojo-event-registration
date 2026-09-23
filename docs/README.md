# CoderDojo Belgium — Help Centre (Sphinx)

End-user documentation (families, volunteers, dojo teams) — see `../CLAUDE.md`
for developer docs, this is a separate audience. Available in English, French
(`fr`), and Dutch (`nl`).

## Building

```sh
pip install -r requirements.txt
make html-all       # builds build/html/ (en), build/html/fr/, build/html/nl/
```

`make html` alone only builds the English (default) source — use `html-all`
to get all three languages. Served at `/docs/`, `/docs/fr/`, `/docs/nl/` via
the `.devcontainer` nginx proxy (`../.devcontainer/nginx/nginx.conf`).

**If the site is already running and you rebuild `docs/build/`:** nginx
bind-mounts that exact directory into the `proxy` container, and Docker pins
a bind mount to the directory's inode at container-creation time. Recreating
`docs/build/` from scratch (e.g. anything that does the equivalent of
`rm -rf build`) orphans that mount — the running container keeps seeing the
old, now-empty directory until it's recreated:

```sh
docker compose -f ../.devcontainer/docker-compose.yml up -d --force-recreate --no-deps proxy
```

(`--no-deps` matters — a plain `up -d proxy` has, at least once, also
recreated unrelated sibling containers for no obvious reason.) Editing
existing files in place (not deleting the directory) doesn't have this
problem — directory bind mounts, unlike single-*file* bind mounts, resolve
lookups dynamically.

## Adding or changing English content

Just edit the `.rst` files under `source/` as normal. Translations go stale
(not wrong — `.po` files keep the last-translated English text alongside
each translation, so nothing breaks, it just won't reflect your edit until
re-translated). See below.

## Updating French/Dutch translations

1. Extract every translatable string from the English source into `.pot`
   catalogs:

   ```sh
   sphinx-build -b gettext source locale/pot
   ```

2. Merge that into the per-language `.po` catalogs under
   `source/locale/{fr,nl}/LC_MESSAGES/` — adds new strings, marks changed
   ones `fuzzy` (needs re-review), removes obsolete ones. Safe to run
   anytime; it never overwrites existing translations, only flags them:

   ```sh
   sphinx-intl update -p locale/pot -d source/locale -l fr -l nl
   ```

3. Translate. Each `.po` file mirrors one `.rst` source file
   (`gettext_compact = False` in `conf.py`) — open the matching file under
   `source/locale/fr/LC_MESSAGES/` or `.../nl/LC_MESSAGES/` and fill in
   `msgstr ""` for anything new or `fuzzy`. Preserve RST markup exactly
   (`**bold**`, `` :doc:`path` ``, backtick-links) — translate only the
   surrounding prose. Remove the `#, fuzzy` flag once you've confirmed the
   translation is correct.

4. Rebuild (`make html-all`) — Sphinx compiles `.po` → `.mo` automatically
   as part of the build, no separate compile step needed.

There's no CI check that translations stay in sync with English — this is
manual, so a change to `source/**/*.rst` and its translation update should
land in the same commit where practical.
