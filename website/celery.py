import gc
import os

from celery import Celery
from celery.signals import worker_before_create_process

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "website.settings")

app = Celery("website")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
# Periodic jobs are CELERY_BEAT_SCHEDULE in website/settings.py (synced into
# django_celery_beat's tables by the DatabaseScheduler), not
# add_periodic_task() calls here: one place for the whole schedule.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@worker_before_create_process.connect
def freeze_before_fork(**kwargs):
    """Keep what the parent has loaded shared with the processes it forks.

    Every worker process loads all of Django (70-100 MB each), and a forked
    child shares those pages with its parent until it writes to them. Python
    writes to every object its garbage collector looks at, so without this
    each child slowly copies the parent's memory. gc.freeze() moves what's
    loaded now out of the collector's reach. Runs in the parent before every
    fork of a task child (also when one is recycled), and before embedded
    beat's (the pool starts first). DATA_MODEL.md §11, "Sharing the machine
    with the website".
    """
    gc.collect()
    gc.freeze()
