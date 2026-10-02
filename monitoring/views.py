"""/metrics/: the site's measurements in Prometheus's text format, for an
outside collector (CAPACITY.md, "Watching production"). Only with the
METRICS_TOKEN as a bearer token; without a token configured it doesn't
exist (404). It shows counts and sizes, never anything about a person."""

import hmac
import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from . import collect, recorder

logger = logging.getLogger(__name__)


def _authorised(request):
    token = settings.METRICS_TOKEN
    if not token:
        raise Http404
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(given.encode(), token.encode())


def _label(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


class Exposition:
    """Prometheus text format: HELP and TYPE once per metric, then its samples."""

    def __init__(self):
        self.lines = []

    def metric(self, name, kind, help_text, samples):
        self.lines += [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"]
        for labels, value in samples:
            rendered = ",".join(f'{key}="{_label(val)}"' for key, val in labels.items())
            self.lines.append(f"{name}{{{rendered}}} {value}" if rendered else f"{name} {value}")

    def text(self):
        return "\n".join(self.lines) + "\n"


def _database(out):
    tables = collect.database_tables()
    out.metric(
        "coderdojo_db_table_rows",
        "gauge",
        "Rows per table (InnoDB estimate).",
        [({"table": name}, t["rows"]) for name, t in sorted(tables.items())],
    )
    out.metric(
        "coderdojo_db_table_bytes",
        "gauge",
        "Data plus index size per table.",
        [({"table": name}, t["data_bytes"] + t["index_bytes"]) for name, t in sorted(tables.items())],
    )
    status = collect.database_status()
    out.metric(
        "coderdojo_mysql_threads_connected", "gauge", "Open MySQL connections.", [({}, status["Threads_connected"])]
    )
    out.metric(
        "coderdojo_mysql_threads_running",
        "gauge",
        "MySQL connections running a query.",
        [({}, status["Threads_running"])],
    )
    out.metric(
        "coderdojo_mysql_max_used_connections",
        "gauge",
        "Most connections since MySQL started.",
        [({}, status["Max_used_connections"])],
    )
    out.metric(
        "coderdojo_mysql_max_connections", "gauge", "MySQL's connection limit.", [({}, status["max_connections"])]
    )
    out.metric(
        "coderdojo_mysql_questions_total", "counter", "Statements since MySQL started.", [({}, status["Questions"])]
    )
    out.metric(
        "coderdojo_mysql_slow_queries_total",
        "counter",
        "Slow queries since MySQL started.",
        [({}, status["Slow_queries"])],
    )


def _redis(out):
    info = collect.redis_info()
    for key in collect.REDIS_MEMORY:
        out.metric(f"coderdojo_redis_{key}_bytes", "gauge", f"Redis INFO {key}.", [({}, info[key])])
    for key in collect.REDIS_STATS:
        kind = "gauge" if key == "connected_clients" else "counter"
        suffix = "" if kind == "gauge" else "_total"
        out.metric(f"coderdojo_redis_{key}{suffix}", kind, f"Redis INFO {key}.", [({}, info[key])])
    out.metric(
        "coderdojo_redis_keys",
        "gauge",
        "Keys per Redis db (0 cache, 1 Channels, 2 Celery broker).",
        [({"db": db}, count) for db, count in sorted(info["keys"].items())],
    )


def _queues(out):
    out.metric(
        "coderdojo_celery_queue_length",
        "gauge",
        "Tasks waiting per Celery queue.",
        [({"queue": queue}, length) for queue, length in collect.queue_lengths().items()],
    )
    mail = collect.mail_queue()
    out.metric("coderdojo_mail_pending", "gauge", "Mail waiting to be sent.", [({}, mail["pending"])])
    out.metric("coderdojo_mail_sending", "gauge", "Mail claimed by a worker.", [({}, mail["sending"])])
    out.metric(
        "coderdojo_mail_oldest_due_seconds",
        "gauge",
        "How long the oldest due mail has waited.",
        [({}, mail["oldest_due_seconds"])],
    )
    out.metric(
        "coderdojo_websocket_connections",
        "gauge",
        "Open notification WebSockets (approximate).",
        [({}, collect.websocket_connections())],
    )


def _processes(out):
    found = recorder.processes()
    for key, help_text in (
        ("rss", "Resident memory per process."),
        ("pss", "Proportional memory per process (sum these for the real total)."),
        ("max_rss", "Peak resident memory per process."),
    ):
        out.metric(
            f"coderdojo_process_{key}_bytes",
            "gauge",
            help_text,
            [({"role": p["role"], "host": p["host"], "pid": p["pid"]}, p[key]) for p in found if key in p],
        )


def _requests(out):
    views = recorder.requests()
    out.metric(
        "coderdojo_http_requests_total",
        "counter",
        "Requests per view.",
        [({"view": view}, int(c.get("count", 0))) for view, c in sorted(views.items())],
    )
    out.metric(
        "coderdojo_http_request_milliseconds_total",
        "counter",
        "Time spent per view.",
        [({"view": view}, int(c.get("ms", 0))) for view, c in sorted(views.items())],
    )
    out.metric(
        "coderdojo_http_db_queries_total",
        "counter",
        "Database queries per view (divide by the requests for queries per request).",
        [({"view": view}, int(c.get("queries", 0))) for view, c in sorted(views.items())],
    )
    out.metric(
        "coderdojo_http_server_errors_total",
        "counter",
        "5xx responses per view.",
        [({"view": view}, int(c.get("5xx", 0))) for view, c in sorted(views.items())],
    )
    buckets = []
    for view, c in sorted(views.items()):
        buckets += [
            ({"view": view, "le": bound}, int(c.get(f"le_{bound}", 0))) for bound in recorder.DURATION_BUCKETS_MS
        ]
        buckets.append(({"view": view, "le": "+Inf"}, int(c.get("count", 0))))
    out.metric(
        "coderdojo_http_request_duration_ms_bucket", "counter", "Requests per view that took at most `le` ms.", buckets
    )


def _tasks(out):
    tasks = recorder.tasks()
    for field, name, kind, help_text in (
        ("count", "coderdojo_task_runs_total", "counter", "Runs per Celery task."),
        ("seconds", "coderdojo_task_seconds_total", "counter", "Time spent per Celery task."),
        ("failures", "coderdojo_task_failures_total", "counter", "Failed runs per Celery task."),
        ("max_seconds", "coderdojo_task_max_seconds", "gauge", "Longest run per Celery task."),
    ):
        out.metric(name, kind, help_text, [({"task": task}, t.get(field, 0)) for task, t in sorted(tasks.items())])


def _cache(out):
    reads = recorder.cache_reads()
    for field, name, help_text in (
        ("hits", "coderdojo_cache_hits_total", "Reads of each data cache (core.caching) that found it."),
        ("misses", "coderdojo_cache_misses_total", "Reads of each data cache that had to build it."),
    ):
        out.metric(
            name, "counter", help_text, [({"cache": n}, int(c.get(field, 0))) for n, c in sorted(reads.items())]
        )


SECTIONS = {
    "database": _database,
    "redis": _redis,
    "queues": _queues,
    "processes": _processes,
    "requests": _requests,
    "tasks": _tasks,
    "cache": _cache,
}


@never_cache
@require_GET
def metrics(request):
    if not _authorised(request):
        return HttpResponse("Unauthorized", status=401, headers={"WWW-Authenticate": "Bearer"})
    out = Exposition()
    up = []
    for name, section in SECTIONS.items():
        try:
            section(out)
        except Exception:
            logger.exception("Metrics: couldn't read %s", name)
            up.append(({"section": name}, 0))
        else:
            up.append(({"section": name}, 1))
    out.metric("coderdojo_metrics_section_up", "gauge", "Whether each section could be read.", up)
    return HttpResponse(out.text(), content_type="text/plain; version=0.0.4; charset=utf-8")
