"""The charts in CAPACITY.md and the technical PDF, from a summary made by
loadtest/summarize.py and the projection of `manage.py capacity_report --json`:

    python3 loadtest/charts.py loadtest/results/2026-09-30.json loadtest/results/capacity-2026-09-30.json
    python3 loadtest/charts.py --caching loadtest/results/2026-10-01-caching.json
    python3 loadtest/charts.py --level27 loadtest/results/2026-10-08-level27-realistic.json

Writes PNGs to loadtest/charts/. Needs matplotlib (loadtest/requirements.txt).
The run names below are the ones of 30 September 2026; a new round of runs
uses the same names (CAPACITY.md, "Measuring again") or edits RUNS. --level27
is the one-off rerun against Level27's real `max_user_connections` (32) and
worker count (3), kept separate from RUNS/MYSQL_MAX_CONNECTIONS so it doesn't
disturb the quarterly devcontainer measurement above; re-run the same way if
the real limit or worker count changes (CAPACITY.md, "Rerun against Level27's
real limits")."""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).with_name("charts")

# The validated reference palette: three categorical slots, the status colours
# (always with a text label), and neutral inks for text and chrome.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
GOOD, WARNING, CRITICAL, OTHER = "#0ca30c", "#fab219", "#d03b3b", "#b4b2a7"
SURFACE, INK, INK_2, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"

RUNS = {
    "workers": ["A100", "B300", "D300w4"],
    "rush": ["G-rush-l100000", "G-rush-l25", "R-rush-l10", "G-rush150-l25"],
    "normal": ["M-l25", "M-l10", "M-l25-keepalive"],
    "memory": "D300w4",
}
MYSQL_MAX_CONNECTIONS = 151

# The 8 Oct 2026 rerun against Level27's real limits: 3 web workers (not 4),
# max_user_connections 32 (not the devcontainer's 151 default). Separate
# constants so this one-off doesn't touch the quarterly measurement above.
LEVEL27_RUNS = {
    "rush": ["rush-cap25", "rush-nocap", "rush-cap10", "rush-cap8"],
    "normal": ["normal-cap25", "normal-cap10", "normal-cap8"],
    "connections": ["rush-cap25", "rush-cap8"],
}
LEVEL27_MAX_CONNECTIONS = 32

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "axes.edgecolor": AXIS,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlepad": 12,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "legend.frameon": False,
        "lines.linewidth": 2,
    }
)


def figure(title, subtitle, width=8, height=4.2):
    """A chart with its claim as the title and what was measured under it."""
    fig, ax = plt.subplots(figsize=(width, height))
    fig.text(0.012, 0.975, title, fontsize=12, fontweight="bold", va="top")
    fig.text(0.012, 0.915, subtitle, fontsize=8.5, color=INK_2, va="top")
    return fig, ax


def save(fig, name, out=OUT):
    out.mkdir(exist_ok=True)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(out / f"{name}.png", dpi=180)
    plt.close(fig)
    print(out / f"{name}.png")


def workers(runs):
    """Response times with 2 and 4 web workers: the number that matters."""
    fig, ax = figure(
        "More web workers keep pages fast under the same load",
        "Mixed load (visitors, families booking, teams taking attendance); response times in ms.",
    )
    chosen = [runs[name] for name in RUNS["workers"]]
    width = 0.26
    for i, (key, label) in enumerate(
        (("p50_ms", "Median"), ("p95_ms", "95th percentile"), ("p99_ms", "99th percentile"))
    ):
        xs = [x + (i - 1) * (width + 0.02) for x in range(len(chosen))]
        values = [run[key] for run in chosen]
        bars = ax.bar(xs, values, width, color=SERIES[i], label=label)
        if key == "p95_ms":
            ax.bar_label(bars, labels=[f"{v:.0f}" for v in values], padding=3, color=INK, fontsize=9)
    ax.set_xticks(range(len(chosen)), [f"{r['label']}\n{r['rps']:.0f} requests/s" for r in chosen])
    ax.set_ylabel("ms")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    save(fig, "web-workers")


def rush_connections(runs):
    fig, ax = figure(
        "The cap keeps MySQL's connections under its limit during a rush",
        "500 families signing up for the same five sessions, 4 web workers. MySQL connections, sampled every 2 s.",
    )
    for colour, name in zip((SERIES[1], SERIES[0]), RUNS["rush"][:2], strict=True):
        run = runs[name]
        points = [
            (t, n) for t, n in zip(run["metrics"]["t"], run["metrics"]["db_connections"], strict=True) if n is not None
        ]
        ts, ns = zip(*points, strict=True)
        ax.plot(ts, ns, color=colour, label=run["label"])
        ax.annotate(
            run["label"],
            (ts[-1], ns[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            color=INK,
            va="center",
            fontsize=9,
        )
    ax.axhline(MYSQL_MAX_CONNECTIONS, color=INK_2, linestyle=(0, (4, 3)), linewidth=1.2)
    ax.text(2, MYSQL_MAX_CONNECTIONS + 3, f"MySQL's limit ({MYSQL_MAX_CONNECTIONS})", color=INK_2, fontsize=9)
    ax.set_ylim(0, MYSQL_MAX_CONNECTIONS + 20)
    ax.set_xlabel("seconds into the test")
    ax.set_ylabel("open MySQL connections")
    ax.legend(loc="lower right")
    save(fig, "rush-connections")


def rush_connections_level27(runs):
    """Same idea as rush_connections(), against Level27's real numbers."""
    fig, ax = figure(
        "The old cap let connections run past the real limit; 8 doesn't",
        "Rush: 500 families signing up for the same five sessions, 3 web workers. MySQL connections, "
        "sampled every 2 s.",
        width=9,
    )
    for colour, name in zip((SERIES[1], SERIES[0]), LEVEL27_RUNS["connections"], strict=True):
        run = runs[name]
        points = [
            (t, n) for t, n in zip(run["metrics"]["t"], run["metrics"]["db_connections"], strict=True) if n is not None
        ]
        ts, ns = zip(*points, strict=True)
        ax.plot(ts, ns, color=colour, label=run["label"])
    ax.axhline(LEVEL27_MAX_CONNECTIONS, color=INK_2, linestyle=(0, (4, 3)), linewidth=1.2)
    ax.text(
        2, LEVEL27_MAX_CONNECTIONS + 1.5, f"max_user_connections ({LEVEL27_MAX_CONNECTIONS})", color=INK_2, fontsize=9
    )
    ax.set_ylim(0, LEVEL27_MAX_CONNECTIONS + 10)
    ax.set_xlabel("seconds into the test")
    ax.set_ylabel("open MySQL connections")
    ax.legend(loc="lower right")
    save(fig, "rush-connections-level27")


def rush_latency(runs):
    fig, ax = figure(
        "Requests that get in are answered faster with the cap",
        "Same rush; 95th-percentile response time of the requests the site answered (Locust's rolling window), in ms.",
    )
    for colour, name in zip((SERIES[1], SERIES[0]), RUNS["rush"][:2], strict=True):
        run = runs[name]
        points = [(t, p) for t, p in zip(run["history"]["t"], run["history"]["p95_ms"], strict=True) if p]
        ts, ps = zip(*points, strict=True)
        ax.plot(ts, ps, color=colour, label=run["label"])
    ax.set_xlabel("seconds into the test")
    ax.set_ylabel("ms")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right")
    save(fig, "rush-latency")


def outcomes(runs, names, title, subtitle, filename):
    """What happened to every request, as shares of all requests."""
    fig, ax = figure(title, subtitle, height=0.75 * len(names) + 1.6)
    kinds = (
        ("ok", "Answered", GOOD),
        ("refused", "Refused at once (503, the cap)", WARNING),
        ("server_error", "Server error (500)", CRITICAL),
        ("other", "Knock-on failure", OTHER),
    )
    for row, name in enumerate(reversed(names)):
        run = runs[name]
        counts = {"ok": run["requests"] - run["failed"], **run["failures"]}
        left = 0
        for key, label, colour in kinds:
            share = 100 * counts.get(key, 0) / run["requests"]
            if share <= 0:
                continue
            ax.barh(row, share, left=left, color=colour, height=0.6, edgecolor=SURFACE, linewidth=2, label=label)
            if share >= 6:
                ax.text(left + share / 2, row, f"{share:.0f}%", ha="center", va="center", fontsize=9, color=INK)
            left += share
    peaks = [
        f"peak {int(runs[n]['db_peak'])} MySQL connections" if runs[n]["db_peak"] else "" for n in reversed(names)
    ]
    ax.set_yticks(
        range(len(names)), [f"{runs[n]['label']}\n{peak}" for n, peak in zip(reversed(names), peaks, strict=True)]
    )
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of all requests")
    ax.grid(axis="y", visible=False)
    handles, labels = ax.get_legend_handles_labels()
    unique = dict(zip(labels, handles, strict=True))
    ax.legend(
        unique.values(),
        unique.keys(),
        loc="upper center",
        bbox_to_anchor=(0.4, -0.2 if len(names) > 3 else -0.26),
        ncol=2,
        fontsize=9,
    )
    save(fig, filename)


def memory(runs):
    run = runs[RUNS["memory"]]
    fig, ax = figure(
        "Memory under load: the web workers grow, the Celery workers stay flat",
        f"{run['label']}; proportional memory (PSS) of all processes of each kind, in MB.",
    )
    for colour, key, label in (
        (SERIES[0], "web_pss_mb", "Web (gunicorn, 4 workers)"),
        (SERIES[1], "celery_pss_mb", "Celery (both workers)"),
    ):
        points = [(t, v) for t, v in zip(run["metrics"]["t"], run["metrics"][key], strict=True) if v]
        ts, vs = zip(*points, strict=True)
        ax.plot(ts, vs, color=colour, label=label)
        ax.annotate(
            f"{max(vs):.0f} MB peak",
            (ts[-1], vs[-1]),
            xytext=(-4, 7),
            textcoords="offset points",
            ha="right",
            fontsize=9,
            color=INK,
        )
    ax.set_ylim(0, None)
    ax.set_xlabel("seconds into the test")
    ax.set_ylabel("MB")
    ax.legend(loc="lower right")
    save(fig, "memory-under-load")


def growth(projection):
    fig, ax = figure(
        "Database size per scenario: mail text is the lever",
        "Projected size of the database (data and indexes), from manage.py capacity_report.",
    )
    for colour, (name, scenario) in zip(SERIES, projection["scenarios"].items(), strict=True):
        # Binary gigabytes, as capacity_report and CAPACITY.md print them.
        gb = [b / 2**30 for b in scenario["bytes"]]
        cleared = [b / 2**30 for b in scenario["bytes_mail_cleared"]]
        label = f"{name}: {scenario['dojos']} dojos, {scenario['families']:,} families"
        ax.plot(scenario["years"], gb, color=colour, marker="o", markersize=4, label=label)
        ax.plot(scenario["years"], cleared, color=colour, linestyle=(0, (4, 3)))
        ax.annotate(
            f"{gb[-1]:.2f} GB",
            (scenario["years"][-1], gb[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
        )
    ax.set_xlabel("years from now")
    ax.set_ylabel("GB")
    ax.set_ylim(0, None)
    handles, labels = ax.get_legend_handles_labels()
    handles.append(matplotlib.lines.Line2D([], [], color=INK_2, linestyle=(0, (4, 3))))
    labels.append("dashed: mail text cleared after 12 months")
    ax.legend(handles, labels, loc="upper left")
    save(fig, "database-growth")


# The caching comparison (CAPACITY.md, "Caching"): the same runs on the code
# before and after, named before-<run> and after-<run> (loadtest/compare.sh).
CACHING_RUNS = ["W4-300", "W2-300", "rush-500"]


def caching(runs):
    """Before and after the caching work: what each request costs MySQL,
    and the response times."""
    names = [n for n in CACHING_RUNS if f"before-{n}" in runs and f"after-{n}" in runs]
    labels = [runs[f"after-{n}"]["label"].replace(" (after)", "") for n in names]
    width = 0.36

    fig, ax = figure(
        "A third fewer MySQL statements per request",
        "MySQL statements per answered request over the whole run (Celery's and /metrics/'s own included).",
    )
    for i, (side, colour) in enumerate((("before", OTHER), ("after", SERIES[0]))):
        xs = [x + (i - 0.5) * (width + 0.02) for x in range(len(names))]
        values = [runs[f"{side}-{n}"]["database"]["mysql_statements_per_request"] for n in names]
        bars = ax.bar(xs, values, width, color=colour, label=side.capitalize())
        ax.bar_label(bars, labels=[f"{v:.1f}" for v in values], padding=3, color=INK, fontsize=9)
    ax.set_xticks(range(len(names)), labels)
    ax.set_ylabel("statements per request")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right")
    save(fig, "caching-statements")

    fig, ax = figure(
        "Pages answer faster with less work for the database",
        "Median and 95th percentile response times in ms, before (grey) and after (blue) the caching work.",
    )
    for i, (side, colour) in enumerate((("before", OTHER), ("after", SERIES[0]))):
        xs = [x + (i - 0.5) * (width + 0.02) for x in range(len(names))]
        p95 = [runs[f"{side}-{n}"]["p95_ms"] for n in names]
        p50 = [runs[f"{side}-{n}"]["p50_ms"] for n in names]
        bars = ax.bar(xs, p95, width, color=colour, alpha=0.45, label=f"{side.capitalize()}: 95th percentile")
        ax.bar(xs, p50, width, color=colour, label=f"{side.capitalize()}: median")
        ax.bar_label(bars, labels=[f"{v:.0f}" for v in p95], padding=3, color=INK, fontsize=9)
    ax.set_xticks(range(len(names)), labels)
    ax.set_ylabel("ms")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=8.5)
    save(fig, "caching-latency")


def main():
    if sys.argv[1] == "--caching":
        caching(json.load(open(sys.argv[2]))["runs"])
        return
    if sys.argv[1] == "--level27":
        runs = json.load(open(sys.argv[2]))["runs"]
        rush_connections_level27(runs)
        outcomes(
            runs,
            LEVEL27_RUNS["rush"],
            "The old cap (25) was the worst setting tested, not a safe middle ground",
            "What happened to every request in the rush, against production's real 3 workers and "
            "max_user_connections 32.",
            "rush-outcomes-level27",
        )
        outcomes(
            runs,
            LEVEL27_RUNS["normal"],
            "Lowering the cap trades a few clean refusals for zero real errors",
            "300 users, ordinary heavy load (not a rush) — the old cap (25) refused nothing, but had no "
            "headroom left for a rush.",
            "normal-outcomes-level27",
        )
        return
    runs = json.load(open(sys.argv[1]))["runs"]
    workers(runs)
    rush_connections(runs)
    rush_latency(runs)
    outcomes(
        runs,
        RUNS["rush"],
        "In a rush, the cap turns server errors into quick refusals",
        "500 (or 150) families signing up for the same five sessions at once, 4 web workers. Share of all requests.",
        "rush-outcomes",
    )
    outcomes(
        runs,
        RUNS["normal"],
        "Cap 25 refuses nothing under normal heavy load; 10 is too tight",
        "300 users, mixed load, 4 web workers. Connections a proxy keeps open count against the cap too.",
        "cap-normal-load",
    )
    memory(runs)
    if len(sys.argv) > 2:
        growth(json.load(open(sys.argv[2])))


if __name__ == "__main__":
    main()
