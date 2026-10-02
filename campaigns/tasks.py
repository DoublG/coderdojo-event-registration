"""The campaigns app's Celery tasks. They keep the names they had in
mailing.tasks (`name=`), so the beat schedule (CELERY_BEAT_SCHEDULE, its
PeriodicTask rows) and any task already waiting in the broker during a
deploy still find them."""

from celery import shared_task


@shared_task(name="mailing.tasks.launch_campaign")
def launch_campaign(campaign_id, cursor=0):
    """Queue one chunk of a launched campaign's mail, then the next chunk as
    a new task at the back of the queue (default queue): the mailing worker
    sends what's waiting in between, so booking mail never waits for a whole
    campaign (CAPACITY.md, finding 8)."""
    from .services import queue_chunk

    queued, next_cursor = queue_chunk(campaign_id, cursor)
    if next_cursor is not None:
        launch_campaign.delay(campaign_id, next_cursor)
    return queued


@shared_task(name="mailing.tasks.launch_due_campaigns")
def launch_due_campaigns():
    """Beat, every minute (periodic queue, so it stays quick): hands due and
    interrupted campaigns to launch_campaign and completes finished ones."""
    from .services import launch_due

    return len(launch_due())


@shared_task(name="mailing.tasks.run_journeys")
def run_journeys():
    """Daily (default queue): send each active journey to those newly due."""
    from .journeys import run

    return run()
