"""The charts in CODING_STANDARDS.md and the technical PDF, from a summary
made by quality/summarize.py, in the load-test charts' style (loadtest/charts.py):

    <venv>/bin/python quality/charts.py quality/results/2026-10-01.json
    <venv>/bin/python quality/charts.py --memory quality/results/memory-2026-10-03.json   # MEMORY.md

Writes PNGs to quality/charts/. Needs matplotlib (loadtest/requirements.txt)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "loadtest"))
from charts import INK, INK_2, SERIES, figure, save  # noqa: E402

OUT = Path(__file__).with_name("charts")
# One hue, light to dark: a higher complexity rank is "more", not another kind.
RANK_COLOURS = {"A": "#b9d3f2", "B": "#86b3ea", "C": "#5592de", "D": "#2a78d6", "E": "#1f5aa3", "F": "#163f73"}
SITE, DEV = SERIES[0], SERIES[1]


def coverage_per_app(summary):
    cov = summary["coverage"]
    apps = sorted(cov["apps"].items(), key=lambda item: item[1]["site_percent"] or 0)
    fig, ax = figure(
        f"Test coverage: {cov['site_percent']:.0f}% of the site's code, {cov['percent']:.0f}% with the seeders",
        "Statements and branches the tests run, per app. Seeders and imports run on developers' machines only.",
        height=0.42 * len(apps) + 1.8,
    )
    rows = range(len(apps))
    site = [app["site_percent"] or 0 for _, app in apps]
    everything = [app["percent"] for _, app in apps]
    bars = ax.barh([r + 0.2 for r in rows], site, height=0.38, color=SITE, label="the site's own code")
    ax.bar_label(bars, labels=[f"{v:.0f}%" for v in site], padding=3, fontsize=8.5, color=INK)
    bars = ax.barh([r - 0.2 for r in rows], everything, height=0.38, color=DEV, label="with seeders and commands")
    ax.bar_label(bars, labels=[f"{v:.0f}%" for v in everything], padding=3, fontsize=8.5, color=INK)
    ax.set_yticks(list(rows), [name for name, _ in apps])
    ax.set_xlim(0, 108)
    ax.set_xlabel("% covered")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.1), ncol=2)
    save(fig, "coverage-per-app", OUT)


def complexity_ranks(summary):
    comp = summary["complexity"]
    ranks = comp["ranks"]
    fig, ax = figure(
        f"Most functions are simple: {100 * ranks['A'] / comp['functions']:.0f}% rank A",
        f"Cyclomatic complexity of {comp['functions']:,} functions and methods (radon): "
        "A 1–5, B 6–10, C 11–20, D 21–30, E 31–40, F over 40.",
    )
    bars = ax.bar(list(ranks), list(ranks.values()), color=[RANK_COLOURS[r] for r in ranks], width=0.6)
    ax.bar_label(bars, labels=[f"{n:,}" for n in ranks.values()], padding=3, fontsize=9, color=INK)
    ax.set_ylabel("functions")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_yticks([0, 10, 100, 1000])
    ax.set_yticklabels(["0", "10", "100", "1,000"])
    ax.grid(axis="x", visible=False)
    save(fig, "complexity-ranks", OUT)


def most_complex(summary, count=12):
    functions = summary["complexity"]["most_complex"][:count]
    fig, ax = figure(
        "Only seed code is over 20: every function of the site stays under it",
        "Cyclomatic complexity per function; seeders and import commands only run on a developer's machine.",
        height=0.34 * count + 1.8,
    )
    labels = [f"{f['path'].rsplit('/', 1)[-1]}: {f['name']}" for f in reversed(functions)]
    colours = [DEV if f["kind"].startswith("seed") else SITE for f in reversed(functions)]
    bars = ax.barh(labels, [f["complexity"] for f in reversed(functions)], color=colours, height=0.6)
    ax.bar_label(bars, padding=3, fontsize=9, color=INK)
    ax.axvline(20, color=INK_2, linestyle=(0, (4, 3)), linewidth=1.2)
    ax.text(20.5, count - 0.45, "over 20 fails the lint (seed code excepted)", color=INK_2, fontsize=8.5)
    ax.set_xlabel("cyclomatic complexity")
    ax.grid(axis="y", visible=False)
    from matplotlib.patches import Patch

    ax.legend(
        [Patch(color=SITE), Patch(color=DEV)],
        ["the site", "seeders (development only)"],
        loc="upper center",
        bbox_to_anchor=(0.3, -0.12),
        ncol=2,
    )
    save(fig, "most-complex", OUT)


def plain_log_axis(ax):
    from matplotlib.ticker import FuncFormatter

    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))


def megabytes(n):
    return f"{n / 1e6:.1f} MB" if n >= 1e5 else f"{n / 1e3:.0f} KB"


def memory_functions(profile, count=15):
    """The functions with the highest peak per call (quality/memory_profile.py).
    Callers repeat their callee's peak, so only the deepest function of each
    chain of tasks and middleware is shown."""
    skip = ("Middleware.__call__", "tasks.py")
    functions = [f for f in profile["functions"] if not f["name"].endswith(skip) and not f["path"].endswith(skip)]
    functions = functions[:count]
    top, next_top = functions[0], next(f for f in functions if not f["path"].endswith("engagement.py"))
    fig, ax = figure(
        f"The engagement rebuild needs the most: {megabytes(top['peak'])}, "
        f"{top['peak'] / next_top['peak']:.0f}× the heaviest page",
        f"Highest peak per call of the site's functions (Python allocations, tracemalloc), on "
        f"{profile['database']['children']:,} children and {profile['database']['registrations']:,} bookings. "
        "Log scale.",
        height=0.34 * count + 1.8,
    )
    labels = [f"{f['path'].rsplit('/', 1)[-1]}: {f['name']}" for f in reversed(functions)]
    peaks = [f["peak"] / 1e6 for f in reversed(functions)]
    bars = ax.barh(labels, peaks, color=SITE, height=0.6)
    ax.bar_label(bars, labels=[megabytes(f["peak"]) for f in reversed(functions)], padding=3, fontsize=8.5, color=INK)
    ax.set_xscale("log")
    ax.set_xlim(0.1, max(peaks) * 4)
    plain_log_axis(ax)
    ax.set_xlabel("peak per call, MB (log scale)")
    ax.grid(axis="y", visible=False)
    save(fig, "memory-functions", OUT)


def memory_steps(profile, count=15):
    """The pages, writes and jobs with the highest peak."""
    steps = [s for s in profile["steps"] if s["kind"] != "page" or s.get("status") in (200, 302)]
    highest = {}
    for step in sorted(steps, key=lambda s: -s["peak"]):  # the highest of each page or job run twice
        highest.setdefault(step["label"], step)
    steps = list(highest.values())[:count]
    colour = {"page": SERIES[0], "job": SERIES[1]}
    pages = max(s["peak"] for s in steps if s["kind"] == "page")
    fig, ax = figure(
        f"Pages need at most {megabytes(pages)}; the heaviest nightly job takes {megabytes(steps[0]['peak'])}",
        "Highest memory above the start of each page, write or job, served once on the scale database. Log scale.",
        height=0.34 * count + 2.0,
    )
    labels = [s["label"].replace("mailing.tasks.", "").replace("events.tasks.", "")[:58] for s in reversed(steps)]
    bars = ax.barh(
        labels,
        [s["peak"] / 1e6 for s in reversed(steps)],
        color=[colour.get(s["kind"], SERIES[2]) for s in reversed(steps)],
        height=0.6,
    )
    ax.bar_label(bars, labels=[megabytes(s["peak"]) for s in reversed(steps)], padding=3, fontsize=8.5, color=INK)
    ax.set_xscale("log")
    ax.set_xlim(0.1, max(s["peak"] for s in steps) / 1e6 * 4)
    plain_log_axis(ax)
    ax.set_xlabel("peak, MB (log scale)")
    ax.grid(axis="y", visible=False)
    from matplotlib.patches import Patch

    ax.legend(
        [Patch(color=SERIES[0]), Patch(color=SERIES[1]), Patch(color=SERIES[2])],
        ["page", "background job", "write, campaign or other"],
        loc="upper center",
        bbox_to_anchor=(0.3, -0.1),
        ncol=3,
    )
    save(fig, "memory-steps", OUT)


def main():
    if sys.argv[1] == "--memory":
        profile = json.load(open(sys.argv[2]))
        memory_functions(profile)
        memory_steps(profile)
        return
    summary = json.load(open(sys.argv[1]))
    coverage_per_app(summary)
    complexity_ranks(summary)
    most_complex(summary)


if __name__ == "__main__":
    main()
