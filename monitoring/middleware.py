import logging
import time

from django.conf import settings

from . import recorder

logger = logging.getLogger(__name__)


class RequestMetricsMiddleware:
    """Times every request per view (monitoring.recorder), logs the slow
    ones and lets the process report its memory once a minute. First in
    MIDDLEWARE, so the time covers the whole stack."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)
        milliseconds = (time.perf_counter() - started) * 1000
        match = getattr(request, "resolver_match", None)
        view = (match.view_name if match else None) or "unresolved"
        recorder.record_request(view, milliseconds, response.status_code)
        if milliseconds >= settings.METRICS_SLOW_REQUEST_MS:
            logger.warning("Slow request: %s %s (%s) took %d ms", request.method, request.path, view, milliseconds)
        recorder.report_process("web")
        return response
