import logging
import time

from django.conf import settings
from django.db import connection

from . import recorder

logger = logging.getLogger(__name__)


class _QueryCounter:
    """A database execute wrapper that counts the statements run."""

    def __init__(self):
        self.count = 0

    def __call__(self, execute, sql, params, many, context):
        self.count += 1
        return execute(sql, params, many, context)


class RequestMetricsMiddleware:
    """Times every request per view (monitoring.recorder), counts its
    database queries and data cache reads (core.caching), logs the slow
    ones and has the process report its memory (once a minute, from its own
    thread). First in MIDDLEWARE, so the time covers the whole stack."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        recorder.begin_request()
        queries = _QueryCounter()
        with connection.execute_wrapper(queries):
            response = self.get_response(request)
        milliseconds = (time.perf_counter() - started) * 1000
        match = getattr(request, "resolver_match", None)
        view = (match.view_name if match else None) or "unresolved"
        recorder.record_request(view, milliseconds, response.status_code, queries.count, recorder.end_request())
        if milliseconds >= settings.METRICS_SLOW_REQUEST_MS:
            logger.warning("Slow request: %s %s (%s) took %d ms", request.method, request.path, view, milliseconds)
        recorder.start_reporting("web")
        return response
