# Perspective, served from our own static files

The pivot table and chart builder of the organisation's reports
(`reports`, DATA_MODEL_REPORTS.md §30): unchanged copies of files from the
npm packages, so the report pages never load anything from a CDN.
Apache-2.0 (`LICENSE.md`, identical in every package). Only the files a
browser needs are here: no source maps, types or Node builds, and only the
two themes the site uses. The folders keep the packages' own layout
(`<package>/dist/...`), because the client finds the server's WebAssembly
by rewriting its own URL from `/client/dist/cdn/` to `/server/dist/wasm/`.

| File | npm package | Path in the package |
|---|---|---|
| `client/dist/cdn/perspective.js`, `perspective-server.worker.js` | `@perspective-dev/client@5.5.1` | the same |
| `client/dist/wasm/perspective-js.wasm` | `@perspective-dev/client@5.5.1` | the same |
| `server/dist/wasm/perspective-server.wasm`, `perspective-server.memory64.wasm` | `@perspective-dev/server@5.5.1` | the same |
| `viewer/dist/cdn/perspective-viewer.js`, `viewer/dist/wasm/perspective-viewer.wasm` | `@perspective-dev/viewer@5.5.1` | the same |
| `viewer/dist/css/pro.css`, `pro-dark.css`, `intl/fr.css` | `@perspective-dev/viewer@5.5.1` | the same |
| `viewer-datagrid/dist/cdn/perspective-viewer-datagrid.js` | `@perspective-dev/viewer-datagrid@5.5.1` | the same |
| `viewer-charts/dist/cdn/perspective-viewer-charts.js` | `@perspective-dev/viewer-charts@5.5.1` | the same |

The older `@finos/perspective-*` packages are deprecated in favour of these.
The Dutch interface texts are ours, not in the package:
`reports/static/reports/perspective-nl.css`.

## What the pages' security policy allows for it

Only the report pages (`reports.views.perspective_policy`, checked by
`reports.tests.ReportPageTests`): `'wasm-unsafe-eval'` and `blob:` in
`script-src`, and `worker-src 'self' blob:`. The bundles start their
WebAssembly glue and their workers (the engine's, the chart renderer's) from
`blob:` URLs; without `blob:` the viewer doesn't start, and inside the chart
renderer's worker a blocked import fails silently: the chart stays empty.
The viewer also contains an optional AI chat that calls outside APIs when
someone enters a key for one; `connect-src 'self'` blocks those calls.

## Upgrading

1. Download each package tarball (`client`, `server`, `viewer`,
   `viewer-datagrid`, `viewer-charts`, all the same version) and check it
   against the registry's own checksum:

   ```sh
   p=viewer v=<version>
   curl -sfO https://registry.npmjs.org/@perspective-dev/$p/-/$p-$v.tgz
   curl -sf https://registry.npmjs.org/@perspective-dev/$p/$v | python3 -c 'import sys,json; print(json.load(sys.stdin)["dist"]["integrity"])'
   echo "sha512-$(openssl dgst -sha512 -binary $p-$v.tgz | base64 -w0)"   # must match
   ```

2. Copy the files in the table into a new folder `perspective-<version>/`,
   delete the old folder, and update the version in `reports/static/reports/report.js`'s
   imports and in `reports/templates/reports/report_detail.html`'s stylesheets.
   `reports.tests.VendoredPerspectiveTests` fails while an import points at a
   missing file.
3. Compare the new `viewer/dist/css/intl.css` with `perspective-nl.css` and
   translate what's new.
4. Open a report in each language and theme, with a table and a chart, and
   check the browser console; update the version and date in `MAINTENANCE.md`.
