"""Personal data in Django's and third-party apps' models (DATA_MODEL.md §16).
Our own apps declare theirs in their own privacy.py."""

from auditlog.models import LogEntry as AuditLogEntry
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django_celery_beat.models import (
    ClockedSchedule,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    PeriodicTasks,
    SolarSchedule,
)
from django_celery_results.models import ChordCounter, GroupResult, TaskResult

from privacy.models import ErasureRecord, RetentionNotice
from privacy.registry import Category, LegalBasis, Subject, keep, personal, register, register_not_personal

register(
    Session,
    purpose="Keeping someone logged in, and their language choice",
    legal_basis=LegalBasis.CONTRACT,
    retention="login_session",
    seen_by="Nobody reads it; the site itself",
    fields={
        ("session_key", "session_data"): personal(Category.SECURITY, export=False),
        "expire_date": personal(Category.SECURITY, export=False),
    },
)

register(
    LogEntry,
    purpose="Tracing changes made by hand in the Django admin",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="admin_log",
    seen_by="The organisation (Django admin)",
    fields={
        "user": keep(Category.IDENTITY, "points at the anonymised account of whoever made the change", export=False),
        # object_repr and change_message can name the person whose row was changed.
        ("object_repr", "change_message"): personal(Category.IDENTITY, export=False),
        "action_time": keep(Category.IDENTITY, "when a change was made stays traceable", export=False),
    },
    not_personal=["id", "content_type", "object_id", "action_flag"],
)

register(
    AuditLogEntry,
    purpose="The audit log: who changed what, and who viewed health notes or criminal-record extracts",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="audit_log",
    seen_by="The organisation's admin role (Django admin)",
    fields={
        # Diffs and names of the changed rows; the health notes and secrets are masked.
        ("object_repr", "changes", "changes_text", "serialized_data", "additional_data"): personal(
            Category.IDENTITY, export=False
        ),
        ("actor", "actor_email"): personal(Category.IDENTITY, export=False),
        ("timestamp", "action"): keep(
            Category.IDENTITY, "what happened when, once the entry is anonymised", export=False
        ),
    },
    # remote_addr and remote_port stay empty (core.audit, AUDITLOG_DISABLE_REMOTE_ADDR).
    not_personal=["id", "content_type", "object_pk", "object_id", "cid", "remote_addr", "remote_port"],
)

register(
    TaskResult,
    purpose="Results of background tasks that ask for one (most don't)",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="task_result",
    seen_by="The organisation (Django admin)",
    fields={
        # Arguments and results can hold ids or addresses.
        ("task_args", "task_kwargs", "result", "traceback", "meta"): personal(Category.IDENTITY, export=False),
    },
    not_personal=[
        "id",
        "task_id",
        "periodic_task_name",
        "task_name",
        "status",
        "worker",
        "content_type",
        "content_encoding",
        "date_created",
        "date_started",
        "date_done",
    ],
)

register(
    GroupResult,
    purpose="Results of groups of background tasks",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="task_result",
    seen_by="The organisation (Django admin)",
    fields={"result": personal(Category.IDENTITY, export=False)},
    not_personal=["id", "group_id", "date_created", "date_done", "content_type", "content_encoding"],
)

register_not_personal(ChordCounter, "counts finished subtasks of a group, by task id")
register_not_personal(Group, "the permission groups of the organisation roles")
register_not_personal(Permission, "Django's permission list")
register_not_personal(ContentType, "Django's list of models")
for model in (ClockedSchedule, CrontabSchedule, IntervalSchedule, SolarSchedule, PeriodicTasks):
    register_not_personal(model, "the background jobs' schedule")
register_not_personal(PeriodicTask, "the background jobs; their arguments never name a person")

register(
    ErasureRecord,
    purpose="Erasing a person again after a backup is restored",
    legal_basis=LegalBasis.LEGAL_OBLIGATION,
    retention="erasure_log",
    seen_by="The organisation (Django admin)",
    fields={
        # Only which row it was: never who.
        ("model", "object_id", "keep_visible", "reason", "erased_at"): keep(
            Category.IDENTITY, "needed to erase the row again after a backup is restored", export=False
        ),
        "requested_by": keep(Category.IDENTITY, "points at the anonymised account of the admin", export=False),
    },
    not_personal=["id"],
)

register(
    RetentionNotice,
    subjects={Subject.ACCOUNT: "account"},
    purpose="Telling an account it will be deleted for not logging in, a month ahead",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="account",
    seen_by="The organisation (Django admin; champions under Needs attention on the Privacy page)",
    fields={("account", "inactive_since", "days_before", "created_at"): personal(Category.IDENTITY)},
    not_personal=["id"],
)
