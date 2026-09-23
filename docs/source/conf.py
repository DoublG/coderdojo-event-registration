# Configuration file for the Sphinx documentation builder.
#
# This is the *end-user* help site for CoderDojo Belgium's event
# registration platform (families, volunteers, dojo teams) — not developer
# documentation. For that, see /CLAUDE.md at the repo root.

project = "CoderDojo Belgium — Help Centre"
copyright = "CoderDojo Belgium"
author = "CoderDojo Belgium"

extensions = [
    "sphinx.ext.duration",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]
html_title = "CoderDojo Belgium — Help Centre"

# Plain prose for a general audience, not an API reference — no module index,
# no genindex-style clutter.
html_show_sourcelink = False
