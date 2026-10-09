from celery import shared_task

from .retention import apply_retention as _apply_retention


@shared_task
def apply_retention() -> dict[str, int]:
    """The nightly retention job (privacy.retention, DATA_MODEL.md §16 phase 4)."""
    return _apply_retention()
