"""Record which code each user-journey PDF shows: user-journeys/manifest.json.

For every persona, the pages its screenshots came from (the URLs in .shots/en/<persona>/journey.json)
are resolved to their view functions, and the templates each view renders are read from its source.
Each view and template is stored with a fingerprint of its code, so check_journeys.py can tell later
which PDFs show code that has changed since. Run it inside the workspace container, from the repo
root, right after regenerating the PDFs:

    python user-journeys/scripts/manifest.py
"""

import inspect
import json
import os
import re
import subprocess
import sys
from datetime import date
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, REPO)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "website.settings")

import django  # noqa: E402

django.setup()

from check_journeys import function_source, sha  # noqa: E402
from django.template.loader import get_template  # noqa: E402
from django.urls import Resolver404, resolve  # noqa: E402

PERSONAS = ["parent", "ninja", "volunteer", "champion", "reviewer", "organisation"]
TEMPLATE_NAME = re.compile(r"""["']([\w\-/]+\.html)["']""")
INCLUDE = re.compile(r"""\{%\s*include\s+["']([\w\-/]+\.html)["']""")


def rel(path):
    return os.path.relpath(path, REPO)


def view_entry(func):
    # A class-based view resolves to as_view()'s wrapper: record the class instead.
    target = getattr(func, "view_class", None) or inspect.unwrap(func)
    path = inspect.getsourcefile(target)
    if not os.path.abspath(path).startswith(REPO + os.sep) or "/site-packages/" in path:
        return None  # a package's view (e.g. Django's own), not ours
    path, name = rel(path), target.__qualname__
    source = function_source(os.path.join(REPO, path), name)
    if source is None:
        return None
    return f"{path}:{name}", sha(source), TEMPLATE_NAME.findall(inspect.getsource(target))


def template_entry(name):
    try:
        path = rel(get_template(name).origin.name)
    except Exception:
        return None
    if path.startswith(".."):  # Django's or a package's template, not ours
        return None
    return path, sha(open(os.path.join(REPO, path), encoding="utf-8").read())


def main():
    commit = subprocess.run(
        ["git", "-c", f"safe.directory={REPO}", "rev-parse", "--short", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.strip()
    manifest = {"generated_from": commit, "generated_on": date.today().isoformat(), "personas": {}}
    for persona in PERSONAS:
        steps = json.load(open(os.path.join(ROOT, ".shots", "en", persona, "journey.json")))["steps"]
        views, templates, pages = {}, {}, []
        for step in steps:
            path = urlsplit(step["url"]).path
            try:
                match = resolve(path)
            except Resolver404:
                continue  # Mailpit and other pages outside Django
            pages.append(path)
            entry = view_entry(match.func)
            if entry is None:
                print(f"{persona}: {path} has no view of ours to follow ({match.func.__qualname__})")
                continue
            key, digest, names = entry
            views[key] = digest
            # The templates it renders, and the partials they {% include %} (not what they extend:
            # a shared base layout would flag every persona).
            names = list(names)
            while names:
                entry = template_entry(names.pop())
                if entry and entry[0] not in templates:
                    templates[entry[0]] = entry[1]
                    names += INCLUDE.findall(open(os.path.join(REPO, entry[0]), encoding="utf-8").read())
        manifest["personas"][persona] = {
            "pages": sorted(set(pages)),
            "views": dict(sorted(views.items())),
            "templates": dict(sorted(templates.items())),
        }
    out = os.path.join(ROOT, "manifest.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    print(out)


if __name__ == "__main__":
    main()
