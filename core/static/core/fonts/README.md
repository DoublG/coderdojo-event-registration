# Fonts, served from our own static files

`tokens.css` names Nunito (body text, `--font-sans`) and Fredoka (headings,
`--font-display`); `fonts.css` makes them load from here, so every visitor
sees them (not only people who have them installed) without a request to
Google Fonts. The page shells link `fonts.css` before `tokens.css` and
preload the two `latin` files, which every page needs.

Both are Google Fonts under the SIL Open Font License 1.1 (`LICENSE` in each
folder), taken from the Fontsource npm packages, checked against the npm
registry's checksum:

| Folder | npm package | Files (renamed) |
|---|---|---|
| `nunito-5.3.0/` | `@fontsource-variable/nunito@5.3.0` | `files/nunito-latin-wght-normal.woff2`, `files/nunito-latin-ext-wght-normal.woff2` |
| `fredoka-5.3.0/` | `@fontsource-variable/fredoka@5.3.0` | `files/fredoka-latin-wght-normal.woff2`, `files/fredoka-latin-ext-wght-normal.woff2` |

The `font-weight` ranges and `unicode-range`s in `fonts.css` are the
package's own (`index.css`). JetBrains Mono (`--font-mono`) isn't shipped:
no page uses the `.code` style, so the fallback monospace font is enough.

## Upgrading

1. Download `https://registry.npmjs.org/@fontsource-variable/<name>/-/<name>-<version>.tgz`
   and check it against the registry's checksum, as for htmx
   (`core/static/core/vendor/htmx/README.md`).
2. Copy the files into a new `<name>-<version>/` folder, delete the old one,
   and update the paths in `fonts.css` and the preload links in
   `core/templates/core/base.html`, `core/templates/core/_manage_base.html`
   and `dojos/templates/dojos/_admin_base.html`. `core.tests.FontsTests`
   fails while any of them points at a missing file.
