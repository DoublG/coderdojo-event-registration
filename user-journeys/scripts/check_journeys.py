"""Which user-journey PDFs may be out of date? Compares user-journeys/manifest.json with the code.

The manifest (written by manifest.py when the PDFs were made) fingerprints every view function and
template each persona's screenshots come from. This lists, per persona, what changed since, and
flags the persona when the change looks substantial: a template that changed by at least
TEMPLATE_LINES lines (counted with git against the manifest's commit), a view or template that is
gone, or VIEWS views that changed. A flag means "look at the flow again", not "regenerate": a
renamed class or a fixed typo doesn't make a screenshot wrong. Plain Python and git, so it runs
anywhere, from the repo root:

    python user-journeys/scripts/check_journeys.py     # exit 1 when a persona is flagged
"""

import ast
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
TEMPLATE_LINES = 10
VIEWS = 2
PDFS = {
    "parent": ("en/1-parent-journey.pdf", "nl/1-ouder.pdf", "fr/1-parent.pdf"),
    "ninja": ("en/2-ninja-journey.pdf", "nl/2-ninja.pdf", "fr/2-ninja.pdf"),
    "volunteer": ("en/3-volunteer-journey.pdf", "nl/3-vrijwilliger.pdf", "fr/3-benevole.pdf"),
    "champion": ("en/4-champion-journey.pdf", "nl/4-champion.pdf", "fr/4-champion.pdf"),
    "reviewer": ("en/5-reviewer-journey.pdf", "nl/5-beoordelaar.pdf", "fr/5-evaluateur.pdf"),
    "organisation": ("en/6-organisation-journey.pdf", "nl/6-organisatie.pdf", "fr/6-organisation.pdf"),
}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def function_source(path, qualname):
    """The source of a top-level function (or Class.method) in a file, or None when it's gone."""
    try:
        source = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return None
    nodes = ast.parse(source).body
    node = None
    for part in qualname.split("."):
        node = next(
            (
                n
                for n in nodes
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and n.name == part
            ),
            None,
        )
        if node is None:
            return None
        nodes = node.body
    return ast.get_source_segment(source, node)


def lines_changed(commit, path):
    out = subprocess.run(
        ["git", "diff", "--numstat", commit, "--", path], cwd=REPO, capture_output=True, text=True
    ).stdout.split()
    return int(out[0]) + int(out[1]) if len(out) >= 2 and out[0].isdigit() else 0


def main():
    manifest = json.load(open(os.path.join(ROOT, "manifest.json")))
    commit = manifest["generated_from"]
    print(f"User-journey PDFs made from {commit} ({manifest['generated_on']}).")
    known = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=REPO, capture_output=True)
    if known.returncode:
        commit = None
        print(
            "That commit isn't in this repository (amended or rebased away?), so changed lines can't be"
            " counted: every changed template counts as substantial. Rerun manifest.py for a new baseline."
        )
    flagged = []
    for persona, entry in manifest["personas"].items():
        notes, substantial, views_changed = [], False, 0
        for key, digest in entry["views"].items():
            path, name = key.split(":")
            source = function_source(os.path.join(REPO, path), name)
            if source is None:
                notes.append(f"view gone: {key}")
                substantial = True
            elif sha(source) != digest:
                notes.append(f"view changed: {key}")
                views_changed += 1
        for path, digest in entry["templates"].items():
            full = os.path.join(REPO, path)
            if not os.path.exists(full):
                notes.append(f"template gone: {path}")
                substantial = True
            elif sha(open(full, encoding="utf-8").read()) != digest:
                if commit is None:
                    notes.append(f"template changed: {path}")
                    substantial = True
                else:
                    n = lines_changed(commit, path)
                    notes.append(f"template changed: {path} ({n} lines)")
                    substantial = substantial or n >= TEMPLATE_LINES
        substantial = substantial or views_changed >= VIEWS
        if substantial:
            flagged.append(persona)
        status = "REVISIT" if substantial else ("minor changes" if notes else "up to date")
        print(f"\n{persona}: {status}")
        for note in notes:
            print(f"  - {note}")
        if substantial:
            print("  PDFs: " + ", ".join(f"user-journeys/{p}" for p in PDFS[persona]))
    if flagged:
        print(
            "\nLook at the flagged flows: if what a persona sees or does changed (a step added, removed or"
            " reordered, a page redesigned), regenerate those PDFs in en, nl and fr (user-journeys/README.md),"
            " then run manifest.py. If not, just run manifest.py to record the new baseline."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
