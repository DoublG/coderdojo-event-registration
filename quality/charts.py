"""The charts in CODING_STANDARDS.md and the technical PDF, from a summary
made by quality/summarize.py, in the load-test charts' style (loadtest/charts.py):

    <venv>/bin/python quality/charts.py quality/results/2026-10-01.json

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


def main():
    summary = json.load(open(sys.argv[1]))
    coverage_per_app(summary)
    complexity_ranks(summary)
    most_complex(summary)


if __name__ == "__main__":
    main()
