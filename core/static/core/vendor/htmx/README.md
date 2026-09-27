# htmx, served from our own static files

Unchanged copies of the npm packages, so pages don't load them from a CDN
(one connection less, and visitors' IP addresses don't go to a third party).
Both are Zero-Clause BSD (`LICENSE`, from the htmx.org package; the
extension comes from the same project, bigskysoftware/htmx-extensions).

| File | npm package | Path in the package |
|---|---|---|
| `htmx-2.0.4.min.js` | `htmx.org@2.0.4` | `dist/htmx.min.js` |
| `htmx-ext-ws-2.0.1.js` | `htmx-ext-ws@2.0.1` | `ws.js` |

The version is in the file name, so an upgrade gets a new URL and no browser
keeps using a cached old copy.

## Upgrading

1. Download the package tarball from the npm registry and check it against
   the registry's own checksum:

   ```sh
   curl -sfO https://registry.npmjs.org/htmx.org/-/htmx.org-<version>.tgz
   curl -sf https://registry.npmjs.org/htmx.org/<version> | python3 -c 'import sys,json; print(json.load(sys.stdin)["dist"]["integrity"])'
   echo "sha512-$(openssl dgst -sha512 -binary htmx.org-<version>.tgz | base64 -w0)"   # must match
   ```

2. Copy the file in under its new versioned name, delete the old one, and
   update the `<script>` tags in `core/templates/core/base.html`,
   `core/templates/core/_manage_base.html` and
   `dojos/templates/dojos/_admin_base.html` (the extension only in the last).
   `core.tests.VendoredHtmxTests` fails while a tag points at a missing file.
