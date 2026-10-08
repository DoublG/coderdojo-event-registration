from celery import shared_task


# Acknowledged when it starts (not when done, as other tasks): a rebuild
# that dies or is stopped isn't handed out again to fail the same way;
# the next night tries again. Ten minutes is far more than it needs (5 s
# at a year's growth); the time limit stops one that's stuck.
@shared_task(acks_late=False, time_limit=10 * 60)
def rebuild_engagement():
    """Nightly (beat, default queue: it reads every registration): recompute
    events.NinjaEngagement, see events.engagement."""
    from .engagement import rebuild

    return rebuild()
