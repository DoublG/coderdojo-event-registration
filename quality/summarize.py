"""Condenses the code-quality measurements into one small JSON file for
CODING_STANDARDS.md, quality/charts.py and the technical PDF: test coverage
(coverage.py's JSON report) per app and per module, and complexity and
maintainability (radon's JSON) per function and module.

    coverage run manage.py test --noinput --debug-mode    # the whole suite, ~8 minutes
    coverage json -o /tmp/coverage.json
    radon cc -j -e "$EXCLUDE" . > /tmp/cc.json && radon mi -j -e "$EXCLUDE" . > /tmp/mi.json
    radon raw -j -e "$EXCLUDE" . > /tmp/raw.json
    python3 quality/summarize.py /tmp/coverage.json /tmp/cc.json /tmp/mi.json /tmp/raw.json \\
        > quality/results/$(date +%F).json

with EXCLUDE="*/migrations/*,*/tests.py,*/tests/*,docs/*,loadtest/*,user-journeys/*,staticfiles/*,media/*"
(the same files coverage leaves out, pyproject.toml's [tool.coverage.run])."""

import json
import sys
from collections import Counter, defaultdict

# What a module is, for reading the gaps: seeders and import commands only
# run on a developer's machine, the rest is the site.
DEV_ONLY = ("seed_", "import_", "seeding.py", "seed_credentials.py", "seed_translations.py", "seed_templates.py")


def kind(path):
    name = path.rsplit("/", 1)[-1]
    if name.startswith(DEV_ONLY) or any(part in path for part in ("/seed_", "seeding")):
        return "seed or import (development only)"
    if "/management/commands/" in path:
        return "management command"
    return "site"


def app_of(path):
    return path.split("/", 1)[0] if "/" in path else "(root)"


def coverage_part(report):
    apps = defaultdict(lambda: Counter())
    site_apps = defaultdict(lambda: Counter())  # without seeders, imports and other commands
    modules = []
    for path, data in report["files"].items():
        s = data["summary"]
        counts = Counter(
            statements=s["num_statements"],
            covered=s["covered_lines"],
            branches=s.get("num_branches", 0),
            covered_branches=s.get("covered_branches", 0),
        )
        apps[app_of(path)].update(counts)
        if kind(path) == "site":
            site_apps[app_of(path)].update(counts)
        modules.append(
            {
                "path": path,
                "kind": kind(path),
                "statements": s["num_statements"],
                "missing": s["missing_lines"],
                "branches": s.get("num_branches", 0),
                "missing_branches": s.get("missing_branches", 0),
                "percent": round(s["percent_covered"], 1),
            }
        )
    totals = report["totals"]

    def percent(c):
        total = c["statements"] + c["branches"]
        return round(100 * (c["covered"] + c["covered_branches"]) / total, 1) if total else 100.0

    return {
        "percent": round(totals["percent_covered"], 1),
        "statements": totals["num_statements"],
        "missing": totals["missing_lines"],
        "branches": totals.get("num_branches", 0),
        "missing_branches": totals.get("missing_branches", 0),
        "apps": {
            app: {**c, "percent": percent(c), "site_percent": percent(site_apps[app]) if site_apps[app] else None}
            for app, c in sorted(apps.items())
            if app != "(root)"
        },
        "site_percent": percent(sum(site_apps.values(), Counter())),
        "modules": sorted(modules, key=lambda m: m["percent"]),
    }


def complexity_part(cc, mi, raw):
    functions = []
    for path, blocks in cc.items():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if block["type"] in ("function", "method"):
                name = f"{block['classname']}.{block['name']}" if block.get("classname") else block["name"]
                functions.append(
                    {
                        "path": path,
                        "line": block["lineno"],
                        "name": name,
                        "complexity": block["complexity"],
                        "rank": block["rank"],
                        "kind": kind(path),
                    }
                )
    ranks = Counter(f["rank"] for f in functions)
    maintainability = sorted(
        (
            {"path": p, "mi": round(v["mi"], 1), "rank": v["rank"]}
            for p, v in mi.items()
            if isinstance(v, dict) and "mi" in v
        ),
        key=lambda m: m["mi"],
    )
    return {
        "functions": len(functions),
        "average": round(sum(f["complexity"] for f in functions) / len(functions), 2) if functions else 0,
        "ranks": {rank: ranks.get(rank, 0) for rank in "ABCDEF"},
        "most_complex": sorted(functions, key=lambda f: -f["complexity"])[:25],
        "maintainability": maintainability,
        "sloc": sum(v["sloc"] for v in raw.values() if isinstance(v, dict)),
        "files": sum(1 for v in raw.values() if isinstance(v, dict)),
    }


def main(coverage_json, cc_json, mi_json, raw_json):
    load = lambda path: json.load(open(path))  # noqa: E731
    return {
        "coverage": coverage_part(load(coverage_json)),
        "complexity": complexity_part(load(cc_json), load(mi_json), load(raw_json)),
    }


if __name__ == "__main__":
    json.dump(main(*sys.argv[1:5]), sys.stdout, indent=1)
