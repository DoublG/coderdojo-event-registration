import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'website.settings')

app = Celery('website')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
# Periodic jobs are CELERY_BEAT_SCHEDULE in website/settings.py (synced into
# django_celery_beat's tables by the DatabaseScheduler), not
# add_periodic_task() calls here: one place for the whole schedule.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()
