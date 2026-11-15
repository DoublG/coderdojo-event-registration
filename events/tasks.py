from celery import shared_task


# Acknowledged when it starts (not when done, as other tasks): a rebuild
# that dies or is stopped isn't handed out again to fail the same way;
# the next night tries again. Ten minutes is far more than it needs (5 s
# at a year's growth); the time limit stops one that's stuck.
@shared_task(acks_late=False, time_limit=10 * 60)
def rebuild_engagement() -> int:
    """Nightly (beat, default queue: it reads every registration): recompute
    events.NinjaEngagement, see events.engagement."""
    from .engagement import rebuild

    return rebuild()


@shared_task
def release_reserved_places() -> int:
    """Every 15 minutes (beat): a session whose held places were released
    since the last run gives them to the children waiting (the families are
    mailed). The work itself is one task per session on the default queue."""
    from django.utils import timezone

    from .models import Event, Registration

    now = timezone.now()
    due = 0
    candidates = Event.objects.filter(status=Event.OPEN, start_time__gt=now, reserved_places__gt=0)
    for event in candidates:
        if event.reserved_released(now) and Registration.objects.filter(event=event, waiting_list=True).exists():
            fill_session.delay(event.pk)
            due += 1
    return due


@shared_task
def fill_session(event_id: int) -> int:
    """Give a session's free places to the children waiting longest."""
    from . import registrations
    from .models import Event

    event = Event.objects.filter(pk=event_id).first()
    return len(registrations.fill_free_places(event)) if event else 0
