"""Condenses the load test runs in a folder (loadtest/run.sh's output) into one
small JSON file for loadtest/charts.py and CAPACITY.md: per run its settings,
the totals, the failures by kind and time series every 2 seconds.

    python3 loadtest/summarize.py loadtest-out > loadtest/results/<date>.json
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def failures(path):
    """Failed requests by kind: refused (503: the concurrency cap), server
    error (500), and other (a knock-on failure, e.g. a login whose page was
    refused, or a dropped connection)."""
    kinds = Counter()
    if path.exists():
        for row in csv.DictReader(path.open()):
            error = row["Error"]
            kind = "refused" if "503" in error else "server_error" if "500" in error else "other"
            kinds[kind] += int(row["Occurrences"])
    return dict(kinds)


def history(path, start):
    """The Aggregated rows of Locust's history, one per 2 seconds."""
    series = {"t": [], "users": [], "rps": [], "failures_per_s": [], "p95_ms": []}
    last = None
    for row in csv.DictReader(path.open()):
        if row["Name"] != "Aggregated":
            continue
        t = int(row["Timestamp"]) - start
        if last is not None and t - last < 2:
            continue
        last = t
        series["t"].append(t)
        series["users"].append(int(row["User Count"]))
        series["rps"].append(round(number(row["Requests/s"]) or 0, 1))
        series["failures_per_s"].append(round(number(row["Failures/s"]) or 0, 1))
        series["p95_ms"].append(number(row["95%"]))
    return series


def metrics(path, start):
    """/metrics/ samples: MySQL connections, web and Celery memory (MB)."""
    series = {"t": [], "db_connections": [], "web_pss_mb": [], "celery_pss_mb": [], "refused": []}
    if not path.exists():
        return series
    for line in path.open():
        sample = json.loads(line)
        series["t"].append(round(sample["t"] - start, 1))
        series["db_connections"].append(sample.get("db_connections"))
        pss = sample.get("pss_mb") or {}
        series["web_pss_mb"].append(pss.get("web"))
        series["celery_pss_mb"].append(pss.get("celery"))
        series["refused"].append(bool(sample.get("refused") or sample.get("error")))
    return series


def database_load(path, requests):
    """What the run cost the database, from the first and last /metrics/
    samples: MySQL statements per answered request (every statement the server ran,
    Celery's and /metrics/'s own included), and per view its requests and
    queries per request, and per data cache its hit rate, where the site
    reports them (since 1 October 2026)."""
    samples = [json.loads(line) for line in path.open()] if path.exists() else []
    samples = [s for s in samples if s.get("mysql_questions") is not None]
    if len(samples) < 2:
        return None
    first, last = samples[0], samples[-1]
    load = {"mysql_statements_per_request": round((last["mysql_questions"] - first["mysql_questions"]) / requests, 2)}
    views = {}
    for view, now in (last.get("views") or {}).items():
        before = (first.get("views") or {}).get(view, {})
        count = now.get("requests", 0) - before.get("requests", 0)
        if count > 0 and "queries" in now:
            views[view] = {
                "requests": count,
                "queries_per_request": round((now["queries"] - before.get("queries", 0)) / count, 2),
            }
    if views:
        load["views"] = views
    caches = {}
    for name, now in (last.get("cache") or {}).items():
        before = (first.get("cache") or {}).get(name, {})
        hits = now.get("hits", 0) - before.get("hits", 0)
        misses = now.get("misses", 0) - before.get("misses", 0)
        if hits + misses:
            caches[name] = {"reads": hits + misses, "hit_rate": round(hits / (hits + misses), 3)}
    if caches:
        load["caches"] = caches
    return load


def summarize(folder):
    runs = {}
    for meta_path in sorted(Path(folder).glob("*.meta.json")):
        meta = json.loads(meta_path.read_text())
        name = meta["name"]
        stats = Path(folder, f"{name}_stats.csv")
        if not stats.exists():
            continue
        total = next(row for row in csv.DictReader(stats.open()) if row["Name"] == "Aggregated")
        hist = Path(folder, f"{name}_stats_history.csv")
        start = int(meta.get("started", 0))
        if hist.exists():
            first = next((row for row in csv.DictReader(hist.open())), None)
            start = int(first["Timestamp"]) if first else start
        runs[name] = {
            **meta,
            "requests": int(total["Request Count"]),
            "failed": int(total["Failure Count"]),
            "rps": round(float(total["Requests/s"]), 1),
            "p50_ms": number(total["50%"]),
            "p95_ms": number(total["95%"]),
            "p99_ms": number(total["99%"]),
            "failures": failures(Path(folder, f"{name}_failures.csv")),
            "history": history(hist, start) if hist.exists() else None,
            "metrics": metrics(Path(folder, f"{name}.metrics.jsonl"), start),
        }
        answered = runs[name]["requests"] - runs[name]["failed"]  # a refused request never reaches Django
        runs[name]["database"] = database_load(Path(folder, f"{name}.metrics.jsonl"), answered or 1)
        sampled = [n for n in runs[name]["metrics"]["db_connections"] if n is not None]
        runs[name]["db_peak"] = max(sampled + [meta.get("db_peak") or 0]) or None
    return runs


if __name__ == "__main__":
    json.dump({"runs": summarize(sys.argv[1])}, sys.stdout, indent=1)
