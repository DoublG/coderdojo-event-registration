import logging

from celery import shared_task
from django.utils import timezone

from . import collect, recorder
from .models import CapacitySample

logger = logging.getLogger(__name__)

# What a sample holds, each read on its own: a component that's down leaves
# its part out rather than losing the day's sample.
PARTS = {
    "tables": collect.database_tables,
    "mysql": collect.database_status,
    "redis": collect.redis_info,
    "queues": collect.queue_lengths,
    "mail": collect.mail_queue,
    "websockets": collect.websocket_connections,
    "processes": recorder.processes,
    "requests": recorder.requests,
    "tasks": recorder.tasks,
}


def take_sample():
    """Today's CapacitySample (replaced if it's taken again the same day)."""
    now = timezone.now()
    data = {}
    for name, read in PARTS.items():
        try:
            data[name] = read()
        except Exception:
            logger.exception("Capacity sample: couldn't read %s", name)
    sample, _ = CapacitySample.objects.update_or_create(
        taken_on=timezone.localdate(now), defaults={"taken_at": now, "data": data}
    )
    return sample


@shared_task
def record_capacity_sample():
    """Daily: the day's CapacitySample, for the growth trend (CAPACITY.md).
    A few quick reads, so it runs on the periodic queue."""
    take_sample()
