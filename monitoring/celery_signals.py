"""Every Celery task's duration and the worker child's memory
(monitoring.recorder), recorded from Celery's own signals."""

import time

from celery.signals import beat_init, task_postrun, task_prerun, worker_ready

from . import recorder

_started = {}


@task_prerun.connect
def _task_started(task_id=None, **kwargs):
    _started[task_id] = time.perf_counter()


@task_postrun.connect
def _task_finished(task_id=None, task=None, state=None, **kwargs):
    started = _started.pop(task_id, None)
    if started is None or task is None:
        return
    recorder.record_task(task.name, time.perf_counter() - started, failed=state == "FAILURE")
    recorder.start_reporting("celery")


# The worker's parent process and the embedded beat never run a task: they
# start reporting when they're up.
@worker_ready.connect
def _worker_started(**kwargs):
    recorder.start_reporting("celery-parent")


@beat_init.connect
def _beat_started(**kwargs):
    recorder.start_reporting("beat")
