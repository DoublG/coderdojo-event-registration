"""What the site measures about its components (CAPACITY.md): the database's
tables, MySQL's own counters, Redis, the Celery queues, the mail queue and
the open WebSockets. Read by /metrics/ and by the daily capacity sample.
Each function answers from one component, so one that's down doesn't stop
the others being read (monitoring.views, monitoring.tasks)."""

from django.conf import settings
from django.db import connection
from django_redis import get_redis_connection

# django-silk's tables (development only) are profiling data, not the site's.
IGNORED_TABLE_PREFIXES = ("silk_",)

MYSQL_STATUS = ("Threads_connected", "Threads_running", "Max_used_connections", "Questions", "Slow_queries")
REDIS_MEMORY = ("used_memory", "used_memory_peak", "used_memory_rss", "maxmemory")
REDIS_STATS = ("evicted_keys", "rejected_connections", "connected_clients", "expired_keys")
# Queues the two workers listen to (CLAUDE.md, "Background jobs").
QUEUES = ("celery", "periodic")


def database_tables():
    """{table: {"rows", "data_bytes", "index_bytes"}} for the site's database.
    `rows` is InnoDB's estimate (fine for sizing, not for counting)."""
    with connection.cursor() as cursor:
        # MySQL 8 otherwise answers from statistics up to a day old.
        cursor.execute("SET SESSION information_schema_stats_expiry = 0")
        cursor.execute(
            "SELECT table_name, table_rows, data_length, index_length FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"
        )
        rows = cursor.fetchall()
    return {
        name: {"rows": int(count or 0), "data_bytes": int(data or 0), "index_bytes": int(index or 0)}
        for name, count, data, index in rows
        if not name.startswith(IGNORED_TABLE_PREFIXES)
    }


def database_status():
    """MySQL's own counters: connections in use and the most since it
    started, queries and slow queries since it started, and its limit."""
    with connection.cursor() as cursor:
        placeholders = ", ".join(["%s"] * len(MYSQL_STATUS))
        cursor.execute(f"SHOW GLOBAL STATUS WHERE Variable_name IN ({placeholders})", MYSQL_STATUS)
        status = {name: int(value) for name, value in cursor.fetchall()}
        cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
        status["max_connections"] = int(cursor.fetchone()[1])
    return status


def redis_info():
    """Redis's memory, its limit and eviction policy, and the keys per db
    (0 cache, 1 Channels, 2 Celery broker: one server for all three)."""
    info = get_redis_connection("default").info()
    result = {key: info.get(key, 0) for key in (*REDIS_MEMORY, *REDIS_STATS)}
    result["maxmemory_policy"] = info.get("maxmemory_policy", "")
    result["version"] = info.get("redis_version", "")
    result["keys"] = {
        int(name[2:]): values.get("keys", 0)
        for name, values in info.items()
        if name.startswith("db") and name[2:].isdigit()
    }
    return result


def queue_lengths():
    """Tasks waiting per Celery queue (the broker keeps each queue as a list)."""
    from website.celery import app

    with app.connection_for_read() as conn:
        client = conn.default_channel.client
        return {queue: client.llen(queue) for queue in QUEUES}


# Figures other apps report to /metrics/, registered from their
# AppConfig.ready() (register_source), so monitoring imports none of them
# (CODING_STANDARDS.md, "Layers"): "mail_queue" from mailing.
_SOURCES = {}


def register_source(name, function):
    _SOURCES[name] = function


def mail_queue():
    """Mail waiting to be sent, and how long the oldest due one has waited
    (mailing.queue_status.snapshot)."""
    source = _SOURCES.get("mail_queue")
    return source() if source else {"pending": 0, "sending": 0, "oldest_due_seconds": 0}


def websocket_connections():
    """Open notification WebSockets, approximately: the members of every
    Channels group. A connection that died without saying goodbye stays in
    its group until channels_redis expires it (a day at most)."""
    import redis

    address = settings.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"][0]["address"]
    client = redis.Redis.from_url(address, socket_timeout=2)
    try:
        return sum(client.zcard(key) for key in client.scan_iter(match="asgi:group:*", count=500))
    finally:
        client.close()
