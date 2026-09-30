"""Counters the site keeps about itself, for /metrics/ and the capacity
samples (CAPACITY.md): request timings per view, task timings per Celery
task, and each process's own memory. They live in the cache's Redis, so
every gunicorn and Celery process adds to the same numbers.

Cumulative counters, like Prometheus's: a scraper works out rates from the
difference between two reads, and a reset (a cache.clear()) is just a
counter starting over. Recording never fails the request or the task it
measures: a Redis that's down only loses the numbers."""

import atexit
import json
import logging
import os
import resource
import socket
import threading
import time

from django.conf import settings
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

REQUESTS_KEY = "metrics:requests"
TASKS_KEY = "metrics:tasks"
PROCESS_KEY_PREFIX = "metrics:process:"
# Upper bounds (milliseconds) of the request-duration histogram.
DURATION_BUCKETS_MS = (50, 100, 250, 500, 1000, 2500, 5000)
# Each process reports its memory every PROCESS_REPORT_EVERY seconds from a
# small thread of its own, and the report expires after PROCESS_TTL: a
# process that's gone (a restart, a recycled Celery child) drops out of the
# totals within that time, and one that exits cleanly removes its report.
PROCESS_REPORT_EVERY = 60
PROCESS_TTL = 150

_reporting_pid = None


def _redis():
    return get_redis_connection("default")


def enabled():
    return getattr(settings, "METRICS_ENABLED", True)


def process_memory():
    """This process's memory in bytes: `rss` (resident, counting pages it
    shares with its forked siblings in full), `pss` (those shared pages
    divided among the processes sharing them, the fair share: sum it over
    processes for the real total) and `max_rss` (the peak resident size,
    what Celery's --max-memory-per-child compares with)."""
    memory = {"max_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
    try:
        with open("/proc/self/smaps_rollup") as rollup:
            for line in rollup:
                key, _, rest = line.partition(":")
                if key in ("Rss", "Pss"):
                    memory[key.lower()] = int(rest.split()[0]) * 1024
    except OSError:
        # No /proc (not Linux): the peak is all there is.
        memory.setdefault("rss", memory["max_rss"])
    return memory


def _process_key(role):
    return f"{PROCESS_KEY_PREFIX}{role}:{socket.gethostname()}:{os.getpid()}"


def report_process(role):
    """Store this process's memory under its role (`web`, `celery`,
    `celery-parent`, `beat`) for PROCESS_TTL seconds."""
    if not enabled():
        return
    try:
        _redis().set(_process_key(role), json.dumps({**process_memory(), "at": int(time.time())}), ex=PROCESS_TTL)
    except Exception:
        logger.debug("Couldn't report process memory", exc_info=True)


def _forget(role):
    try:
        _redis().delete(_process_key(role))
    except Exception:
        logger.debug("Couldn't remove the process report", exc_info=True)


def _keep_reporting(role):
    while True:
        time.sleep(PROCESS_REPORT_EVERY)
        report_process(role)


def start_reporting(role):
    """Report this process's memory now and then every minute, once per
    process (a forked child starts its own). Cheap to call on every request."""
    global _reporting_pid
    if _reporting_pid == os.getpid() or not enabled():
        return
    _reporting_pid = os.getpid()
    report_process(role)
    threading.Thread(target=_keep_reporting, args=(role,), daemon=True, name="metrics-memory").start()
    atexit.register(_forget, role)


def processes():
    """Every process that reported in the last PROCESS_TTL:
    [{"role", "host", "pid", "rss", "pss", "max_rss", "at"}]."""
    found = []
    connection = _redis()
    keys = sorted(connection.scan_iter(match=f"{PROCESS_KEY_PREFIX}*", count=500))
    for key, value in zip(keys, connection.mget(keys) if keys else [], strict=True):
        if value is None:
            continue
        role, host, pid = key.decode()[len(PROCESS_KEY_PREFIX) :].split(":", 2)
        found.append({"role": role, "host": host, "pid": int(pid), **json.loads(value)})
    return found


def record_request(view, milliseconds, status):
    if not enabled():
        return
    fields = {f"{view}|count": 1, f"{view}|ms": int(milliseconds)}
    for bound in DURATION_BUCKETS_MS:
        if milliseconds <= bound:
            fields[f"{view}|le_{bound}"] = 1
    if status >= 500:
        fields[f"{view}|5xx"] = 1
    try:
        pipe = _redis().pipeline(transaction=False)
        for field, amount in fields.items():
            pipe.hincrby(REQUESTS_KEY, field, amount)
        pipe.execute()
    except Exception:
        logger.debug("Couldn't record a request", exc_info=True)


def record_task(name, seconds, failed=False):
    if not enabled():
        return
    try:
        connection = _redis()
        pipe = connection.pipeline(transaction=False)
        pipe.hincrby(TASKS_KEY, f"{name}|count", 1)
        pipe.hincrbyfloat(TASKS_KEY, f"{name}|seconds", seconds)
        if failed:
            pipe.hincrby(TASKS_KEY, f"{name}|failures", 1)
        pipe.hget(TASKS_KEY, f"{name}|max_seconds")
        longest = pipe.execute()[-1]
        if longest is None or seconds > float(longest):
            connection.hset(TASKS_KEY, f"{name}|max_seconds", round(seconds, 3))
    except Exception:
        logger.debug("Couldn't record a task", exc_info=True)


def _read_hash(key):
    """{name: {field: number}} from a hash of "name|field" counters."""
    grouped = {}
    for raw_field, raw_value in _redis().hgetall(key).items():
        name, _, field = raw_field.decode().rpartition("|")
        grouped.setdefault(name, {})[field] = float(raw_value)
    return grouped


def requests():
    return _read_hash(REQUESTS_KEY)


def tasks():
    return _read_hash(TASKS_KEY)
