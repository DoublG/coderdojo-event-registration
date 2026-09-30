"""Counters the site keeps about itself, for /metrics/ and the capacity
samples (CAPACITY.md): request timings per view, task timings per Celery
task, and each process's own memory. They live in the cache's Redis, so
every gunicorn and Celery process adds to the same numbers.

Cumulative counters, like Prometheus's: a scraper works out rates from the
difference between two reads, and a reset (a cache.clear()) is just a
counter starting over. Recording never fails the request or the task it
measures: a Redis that's down only loses the numbers."""

import json
import logging
import os
import resource
import socket
import time

from django.conf import settings
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

REQUESTS_KEY = "metrics:requests"
TASKS_KEY = "metrics:tasks"
PROCESS_KEY_PREFIX = "metrics:process:"
# Upper bounds (milliseconds) of the request-duration histogram.
DURATION_BUCKETS_MS = (50, 100, 250, 500, 1000, 2500, 5000)
# A process reports its memory at most this often, and the report expires
# when the process has been quiet (or gone) for PROCESS_TTL.
PROCESS_REPORT_EVERY = 60
PROCESS_TTL = 15 * 60

_last_process_report = 0.0


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


def report_process(role, force=False, ttl=PROCESS_TTL):
    """Store this process's memory under its role (`web`, `celery`, and
    `celery-parent`/`beat` once at startup), at most once a minute unless
    forced."""
    global _last_process_report
    now = time.time()
    if not enabled() or (not force and now - _last_process_report < PROCESS_REPORT_EVERY):
        return
    _last_process_report = now
    key = f"{PROCESS_KEY_PREFIX}{role}:{socket.gethostname()}:{os.getpid()}"
    try:
        _redis().set(key, json.dumps({**process_memory(), "at": int(now)}), ex=ttl)
    except Exception:
        logger.debug("Couldn't report process memory", exc_info=True)


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
