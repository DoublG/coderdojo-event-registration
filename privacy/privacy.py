"""Personal data in Django's and third-party apps' models (DATA_MODEL.md §16).
Our own apps declare theirs in their own privacy.py."""

from auditlog.models import LogEntry as AuditLogEntry
from django.apps import apps
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
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from oauth2_provider.models import AccessToken, Application, DeviceGrant, Grant, IDToken, RefreshToken
from two_factor.plugins.webauthn.models import WebauthnDevice

from core.privacy_registry import Category, LegalBasis, Subject, keep, personal, register, register_not_personal
from privacy.models import ErasureRecord, RetentionNotice

register(
    Session,
    purpose="Keeping someone logged in, and their language choice (in the database, with a copy in the "
    "cache's Redis that expires with the session)",
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

# The API (DATA_MODEL.md §13) only has the client credentials grant: every
# client and token belongs to a dojo API client's technical account.
for model in (Application, AccessToken, RefreshToken, Grant, IDToken, DeviceGrant):
    register_not_personal(model, "API clients and their tokens, all of technical accounts (client credentials only)")

# Two-step login (DATA_MODEL.md §15, accounts/two_step.py): the account's
# authenticator app, passkeys and backup codes. The export shows which
# methods an account has and when they were used, never a secret.
_SIGN_IN = {
    "subjects": {Subject.ACCOUNT: "user"},
    "legal_basis": LegalBasis.LEGITIMATE_INTEREST,
    "retention": "sign_in_methods",
    "seen_by": "Nobody reads it; the site checks logins against it. The organisation (Django admin)",
}
_DEVICE_FIELDS = {
    ("user", "name", "confirmed", "created_at", "last_used_at"): personal(Category.IDENTITY),
    ("throttling_failure_timestamp", "throttling_failure_count"): personal(Category.SECURITY, export=False),
}
register(
    TOTPDevice,
    purpose="Two-step login with an authenticator app",
    fields={**_DEVICE_FIELDS, "key": personal(Category.SECURITY, export=False)},
    not_personal=["id", "step", "t0", "digits", "tolerance", "drift", "last_t"],
    **_SIGN_IN,
)
register(
    WebauthnDevice,
    purpose="Two-step login with a passkey",
    fields={**_DEVICE_FIELDS, ("public_key", "key_handle", "sign_count"): personal(Category.SECURITY, export=False)},
    not_personal=["id"],
    **_SIGN_IN,
)
register(
    StaticDevice,
    purpose="Two-step login: the holder of the backup codes",
    fields=_DEVICE_FIELDS,
    not_personal=["id"],
    **_SIGN_IN,
)
register(
    StaticToken,
    purpose="Two-step login: the backup codes, each used once",
    fields={"token": personal(Category.SECURITY, export=False)},
    not_personal=["id", "device"],
    **{**_SIGN_IN, "subjects": {Subject.ACCOUNT: "device__user"}},
)


# django-silk: request profiling on the development system only (it's in
# requirements-dev.txt, never in production). It stores whole requests and
# responses and every SQL query, so whatever a page posts or shows can be in
# there: passwords, children's details, health notes. Classified as the
# worst it can hold, never exported, and only while the app is installed.
if apps.is_installed("silk"):
    from silk.models import Profile as SilkProfile
    from silk.models import Request as SilkRequest
    from silk.models import Response as SilkResponse
    from silk.models import SQLQuery as SilkSQLQuery

    _SILK = {
        "purpose": "Development only: profiling the site's speed (django-silk)",
        "legal_basis": LegalBasis.LEGITIMATE_INTEREST,
        "retention": "dev_profiling",
        "seen_by": "Developers, on the development system",
    }
    register(
        SilkRequest,
        **_SILK,
        fields={
            # Headers hold the session and CSRF cookies; bodies and query
            # strings whatever was posted or searched for.
            "encoded_headers": personal(Category.SECURITY, export=False),
            ("query_params", "raw_body", "body"): personal(Category.SPECIAL, export=False),
        },
        not_personal=[
            "id",
            "path",
            "method",
            "start_time",
            "view_name",
            "end_time",
            "time_taken",
            "meta_time",
            "meta_num_queries",
            "meta_time_spent_queries",
            "pyprofile",
            "prof_file",
            "num_sql_queries",
        ],
    )
    register(
        SilkResponse,
        **_SILK,
        fields={
            "encoded_headers": personal(Category.SECURITY, export=False),
            ("raw_body", "body"): personal(Category.SPECIAL, export=False),
        },
        not_personal=["id", "request", "status_code"],
    )
    register(
        SilkSQLQuery,
        **_SILK,
        # The SQL with its parameters: any row a page read or wrote.
        fields={"query": personal(Category.SPECIAL, export=False)},
        not_personal=[
            "id",
            "profiles",
            "start_time",
            "end_time",
            "time_taken",
            "identifier",
            "request",
            "traceback",
            "analysis",
        ],
    )
    register_not_personal(SilkProfile, "timings of profiled code blocks: function names and line numbers")
