from celery import shared_task

from . import admin_access


@shared_task
def close_admin_access() -> int:
    """Every 5 minutes: close Django admin access whose 12 hours are up
    (accounts.admin_access). The admin site already refuses it at the
    minute; this records the end and takes staff status away."""
    return admin_access.close_expired()
