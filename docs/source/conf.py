# Configuration file for the Sphinx documentation builder.
#
# This is the *end-user* help site for CoderDojo Belgium's event
# registration platform (families, volunteers, dojo teams) — not developer
# documentation. For that, see /CLAUDE.md at the repo root.

import os

project = "CoderDojo Belgium — Help Centre"
copyright = "CoderDojo Belgium"
author = "CoderDojo Belgium"

extensions = [
    "sphinx.ext.duration",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# i18n. English (this source) is the default; French/Dutch translations
# live in locale/{fr,nl}/LC_MESSAGES/*.po (see docs/README.md for the
# extract/update/build workflow). gettext_compact=False keeps one .po file
# per .rst source file (matches the docs/source/ layout) rather than one
# combined catalog — easier to see what's translated per page.
language = "en"
locale_dirs = ["locale/"]
gettext_compact = False

html_theme = "furo"
html_static_path = ["_static"]

# Not just `language`: a `-D language=fr` override on the command line only
# patches Sphinx's final config object, it doesn't touch this already-run
# script's own local variables, so `language` here would still read "en"
# regardless of which build invoked it. `-D html_title=...` is passed
# explicitly per language in the build commands instead (see
# docs/README.md) — this is only the English/default fallback.
html_title = "CoderDojo Belgium — Help Centre"

# Plain prose for a general audience, not an API reference — no module index,
# no genindex-style clutter.
html_show_sourcelink = False

# Each language name written in its own language (not translated per-build)
# so it's recognizable regardless of which language you're currently
# reading — same convention as the main site's language switcher
# (core/templates/core/menu.html). Root-relative: this is injected
# unchanged on every page regardless of nesting depth. The devcontainer
# serves the docs at /docs/ (see .devcontainer/nginx/nginx.conf); the
# GitHub Pages build (.github/workflows/docs.yml) sets DOCS_BASE_URL to the
# Pages path instead.
_base = os.environ.get("DOCS_BASE_URL", "/docs/")
html_theme_options = {
    "announcement": (
        f"<a href='{_base}'>English</a> &middot; "
        f"<a href='{_base}fr/'>Fran&ccedil;ais</a> &middot; "
        f"<a href='{_base}nl/'>Nederlands</a>"
    ),
}
