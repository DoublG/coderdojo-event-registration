from celery import shared_task


@shared_task
def rebuild_engagement():
    """Nightly (beat, default queue: it reads every registration): recompute
    events.NinjaEngagement, see events.engagement."""
    from .engagement import rebuild

    return rebuild()
