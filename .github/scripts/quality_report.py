"""The Code quality workflow's report: reads the week's measurement (the JSON
quality/summarize.py makes from coverage.py and radon) and, when there is one,
the previous week's, and writes a summary to the run's page
($GITHUB_STEP_SUMMARY, or the terminal): test coverage in total and per app,
the complexity ranks, the most complex functions and the least maintainable
modules, each with the change since the previous measurement.

A map, not a gate: it never fails the job (CODING_STANDARDS.md, "Complexity").

    python .github/scripts/quality_report.py this-week.json [previous.json]
"""

import json
import os
import sys
from pathlib import Path

TOP = 10  # functions and modules listed
SITE = "site"  # summarize.py's kind for the site's own code (not seeders, imports or commands)
NOT_THE_SITE = ("seed", "import_", "/management/commands/")


def change(now, before, digits=1):
    """' (+0.4)', ' (−2)' or '' when unchanged or nothing to compare with."""
    if before is None:
        return ""
    difference = round(now - before, digits)
    if not difference:
        return ""
    text = f"{abs(difference):.{digits}f}" if digits else f"{abs(int(difference)):,}"
    return f" ({'+' if difference > 0 else '−'}{text})"


def coverage_section(now, before):
    cov, prev = now["coverage"], (before or {}).get("coverage", {})
    lines = [
        "### Test coverage",
        "",
        f"**{cov['site_percent']}%** of the site's own code{change(cov['site_percent'], prev.get('site_percent'))}, "
        f"{cov['percent']}% with seeders and import commands{change(cov['percent'], prev.get('percent'))}; "
        f"{cov['statements']:,} statements.",
        "",
        "| App | The site's code | Everything |",
        "|---|---:|---:|",
    ]
    for app, figures in sorted(cov["apps"].items()):
        old = prev.get("apps", {}).get(app, {})
        lines.append(
            f"| `{app}` | {figures['site_percent']}%{change(figures['site_percent'], old.get('site_percent'))} "
            f"| {figures['percent']}%{change(figures['percent'], old.get('percent'))} |"
        )
    return lines


def complexity_section(now, before):
    cx, prev = now["complexity"], (before or {}).get("complexity", {})
    ranks = " · ".join(
        f"{rank} {count}{change(count, prev.get('ranks', {}).get(rank), 0)}" for rank, count in cx["ranks"].items()
    )
    lines = [
        "### Complexity",
        "",
        f"{cx['functions']:,} functions{change(cx['functions'], prev.get('functions'), 0)}, average "
        f"{cx['average']}{change(cx['average'], prev.get('average'), 2)}; {cx['sloc']:,} lines of code"
        f"{change(cx['sloc'], prev.get('sloc'), 0)}.",
        "",
        f"By rank (radon: A simplest, F most complex): {ranks}. Ruff fails any function over 20 on every push.",
        "",
        "**Most complex functions of the site** (seeders and import commands left out):",
        "",
        "| Function | Complexity | Rank |",
        "|---|---:|:-:|",
    ]
    before_by_name = {(f["path"], f["name"]): f["complexity"] for f in prev.get("most_complex", [])}
    for f in [f for f in cx["most_complex"] if f.get("kind") == SITE][:TOP]:
        old = before_by_name.get((f["path"], f["name"]))
        new = " (new in the list)" if prev and old is None else change(f["complexity"], old, 0)
        lines.append(f"| `{f['path']}:{f['line']}` {f['name']} | {f['complexity']}{new} | {f['rank']} |")
    lines += [
        "",
        "**Least maintainable modules of the site** (radon's maintainability index, 0–100, higher is easier):",
        "",
        "| Module | Index |",
        "|---|---:|",
    ]
    before_mi = {m["path"]: m["mi"] for m in prev.get("maintainability", [])}
    worst = [m for m in cx["maintainability"] if not any(part in m["path"] for part in NOT_THE_SITE)][:TOP]
    for m in worst:
        lines.append(f"| `{m['path']}` | {m['mi']}{change(m['mi'], before_mi.get(m['path']))} |")
    return lines


def report(now, before=None):
    """The summary as Markdown; `before` is the previous measurement or None."""
    compared = "compared with the previous run" if before else "no previous run to compare with"
    lines = [f"## Code quality ({compared})", ""]
    lines += coverage_section(now, before)
    lines += [""]
    lines += complexity_section(now, before)
    return "\n".join(lines) + "\n"


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def main(argv):
    now = load(argv[1]) if len(argv) > 1 else None
    if now is None:
        print("No measurement to report.")
        return 0
    before = load(argv[2]) if len(argv) > 2 else None
    text = report(now, before)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
