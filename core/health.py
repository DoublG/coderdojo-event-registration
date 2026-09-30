"""The health check for uptime monitoring: /health/ answers 200 when the site
can serve people, 503 when it can't, with which check failed. Open to anyone
and never cached; it says nothing beyond "ok"/"error" per check, so it gives
nothing away about the data or the setup."""

import logging

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django_redis import get_redis_connection

from mailing import queue_status

logger = logging.getLogger(__name__)


def check_database():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def check_redis():
    # Not through cache.get(): CACHES' IGNORE_EXCEPTIONS would hide a Redis
    # that's down. The cache, the Channels layer and the Celery broker are
    # all on this one Redis server.
    get_redis_connection("default").ping()


def check_mail_workers():
    # Due mail waiting longer than the Mail queue's threshold means the
    # Celery workers aren't sending (every mail goes through them).
    now = timezone.now()
    if queue_status.is_stalled(queue_status.oldest_due(now), now):
        raise RuntimeError(f"due mail has waited longer than {queue_status.STALLED_AFTER}")


CHECKS = {
    "database": check_database,
    "redis": check_redis,
    "mail_workers": check_mail_workers,
}


@never_cache
@require_GET
def health(request):
    results = {}
    for name, check in CHECKS.items():
        try:
            check()
        except Exception:
            logger.exception("Health check %s failed", name)
            results[name] = "error"
        else:
            results[name] = "ok"
    healthy = all(result == "ok" for result in results.values())
    return JsonResponse(
        {"status": "ok" if healthy else "error", "checks": results},
        status=200 if healthy else 503,
    )
