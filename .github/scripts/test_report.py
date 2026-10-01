"""The Tests workflow's report: reads the test suite's JUnit XML (written by
unittest-xml-reporting's Django runner) and

- writes a summary to the run's page ($GITHUB_STEP_SUMMARY): the totals, a
  table per app, every failed test with its traceback, and the slowest tests;
- marks each failed test on the line of code where it failed (a workflow
  `::error` annotation, shown in the commit's checks and a pull request's
  changed files).

It never fails the job itself: the test step's own result does that.

    python .github/scripts/test_report.py test-results/junit.xml
"""

import html
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

MAX_ANNOTATIONS = 50  # GitHub shows at most 50 per job
MAX_TRACEBACK_LINES = 60
SLOWEST = 10


@dataclass
class Case:
    classname: str
    name: str
    seconds: float
    file: str
    line: int
    outcome: str = "passed"  # passed, failed, error, skipped
    message: str = ""
    details: str = ""

    @property
    def app(self):
        return self.classname.split(".", 1)[0]

    @property
    def label(self):
        return f"{self.classname}.{self.name}"


def read(paths):
    cases = []
    for path in paths:
        for element in ET.parse(path).getroot().iter("testcase"):
            case = Case(
                classname=element.get("classname", ""),
                name=element.get("name", ""),
                seconds=float(element.get("time") or 0),
                file=element.get("file", ""),
                line=int(element.get("line") or 1),
            )
            for outcome, tag in (("failed", "failure"), ("error", "error"), ("skipped", "skipped")):
                found = element.find(tag)
                if found is not None:
                    case.outcome = outcome
                    case.message = found.get("message", "")
                    case.details = (found.text or "").strip()
                    break
            cases.append(case)
    return cases


def failing_line(case, root):
    """Where to mark a failure: the last frame of its traceback inside the
    repository, else the test's own first line."""
    root = str(root).rstrip("/") + "/"
    best = None
    for line in case.details.splitlines():
        line = line.strip()
        if not line.startswith('File "'):
            continue
        path, _, rest = line[6:].partition('", line ')
        number = rest.split(",", 1)[0]
        if path.startswith(root) and "site-packages" not in path and number.isdigit():
            best = (path[len(root) :], int(number))
    return best or (case.file, case.line)


def escape(text, property_value=False):
    """GitHub's workflow-command escaping (a property also escapes : and ,)."""
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if property_value:
        text = text.replace(":", "%3A").replace(",", "%2C")
    return text


def annotations(cases, root):
    lines = []
    for case in [c for c in cases if c.outcome in ("failed", "error")][:MAX_ANNOTATIONS]:
        path, line = failing_line(case, root)
        title = f"{'Failed' if case.outcome == 'failed' else 'Error'}: {case.label}"
        last_line = case.details.splitlines()[-1] if case.details else ""
        message = case.message or last_line or case.outcome
        lines.append(f"::error file={escape(path, True)},line={line},title={escape(title, True)}::{escape(message)}")
    return lines


def duration(seconds):
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes} min {seconds} s" if minutes else f"{seconds} s"


def plural(count, one, many):
    return f"{count:,} {one if count == 1 else many}"


def summary(cases):
    counts = defaultdict(int)
    for case in cases:
        counts[case.outcome] += 1
    total = len(cases)
    took = f"{duration(sum(c.seconds for c in cases))} of test time"
    broken = counts["failed"] + counts["error"]
    if not total:
        headline = "⚠️ No test results were found."
    elif broken:
        parts = [
            f"{counts['failed']:,} failed" if counts["failed"] else "",
            plural(counts["error"], "error", "errors") if counts["error"] else "",
        ]
        headline = f"❌ **{', '.join(p for p in parts if p)}** of {plural(total, 'test', 'tests')} ({took})"
    else:
        headline = f"✅ **All {plural(total, 'test', 'tests')} passed** ({took})"
    if counts["skipped"]:
        headline += f", {counts['skipped']} skipped"
    out = ["## Test results", "", headline, ""]

    per_app = defaultdict(lambda: defaultdict(float))
    for case in cases:
        app = per_app[case.app]
        app["tests"] += 1
        app[case.outcome] += 1
        app["seconds"] += case.seconds
    if per_app:
        out += ["| App | Tests | Failed | Skipped | Time |", "|---|---:|---:|---:|---:|"]
        for name, app in sorted(per_app.items()):
            failed = int(app["failed"] + app["error"])
            out.append(
                f"| `{name}` | {int(app['tests']):,} | {'❌ ' + str(failed) if failed else '0'} "
                f"| {int(app['skipped'])} | {duration(app['seconds'])} |"
            )
        out.append("")

    if broken:
        out += ["### Failed tests", ""]
        for case in [c for c in cases if c.outcome in ("failed", "error")]:
            details = case.details.splitlines()
            if len(details) > MAX_TRACEBACK_LINES:
                details = ["…"] + details[-MAX_TRACEBACK_LINES:]
            out += [
                f"<details><summary><code>{html.escape(case.label)}</code>: "
                f"{html.escape(case.message[:200] or case.outcome)}</summary>",
                "",
                "```",
                *details,
                "```",
                "",
                "</details>",
                "",
            ]

    slowest = sorted(cases, key=lambda c: c.seconds, reverse=True)[:SLOWEST]
    if slowest:
        out += ["<details><summary>The slowest tests</summary>", "", "| Test | Time |", "|---|---:|"]
        out += [f"| `{c.label}` | {c.seconds:.1f} s |" for c in slowest]
        out += ["", "</details>", ""]
    return "\n".join(out)


def main(argv):
    paths = [Path(p) for p in argv[1:]] or sorted(Path("test-results").glob("*.xml"))
    paths = [p for p in paths if p.exists()]
    cases = read(paths)
    root = os.environ.get("GITHUB_WORKSPACE") or os.getcwd()
    for line in annotations(cases, root):
        print(line)
    text = summary(cases)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as out:
            out.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
