"""The audit log (django-auditlog, DATA_MODEL.md §14): who changed what, and
who viewed the most sensitive data. The recorded models are `RECORDED`
below (every other model is listed with its reason in
core.tests.AuditLogCoverageTests); the actor comes from `AuditlogMiddleware`.
It's shown read-only to the organisation's admin role: on the organisation
dashboard (/manage/audit-log/, core.audit_views), with health, criminal-record
and security values hidden (`is_hidden`), and in the Django admin."""

import datetime
from functools import wraps

from auditlog.context import disable_auditlog
from auditlog.middleware import AuditlogMiddleware as BaseAuditlogMiddleware
from auditlog.mixins import AuditlogHistoryAdminMixin
from auditlog.signals import accessed

# Who may see the audit log (the organisation's admin role, accounts/organisation.py).
AUDIT_LOG_PERMISSION = "auditlog.view_logentry"

# The recorded models and their options. `exclude_fields` leaves out what
# the site sets itself; `mask_fields` records that a field changed, never
# its value; `m2m_fields` records many-to-many changes.
USER_OPTIONS = {
    "exclude_fields": ["last_login"],  # every login would be a change
    "mask_fields": ["password", "background_check_token"],
}
# What a two-step login device updates on every login.
_LOGIN_BOOKKEEPING = ["last_used_at", "throttling_failure_timestamp", "throttling_failure_count"]
RECORDED = {
    "accounts.User": {**USER_OPTIONS, "m2m_fields": ["groups", "user_permissions"]},
    # The Background checks admin saves through this proxy of User.
    "applications.BackgroundCheck": USER_OPTIONS,
    # Health data (GDPR art. 9).
    "accounts.Ninja": {"mask_fields": ["allergies_notes"]},
    "accounts.Guardianship": {},
    "accounts.OrganisationRole": {},
    # Time-boxed access to the Django admin (DATA_MODEL.md §23): who asked,
    # why, until when, and how it ended.
    "accounts.AdminAccessGrant": {},
    # Who invited whom to which roles, and when it was accepted or withdrawn.
    "accounts.OrganisationInvitation": {"exclude_fields": ["token_hash"]},
    # The organisation roles' permission groups (accounts/organisation.py).
    "auth.Group": {"m2m_fields": ["permissions"]},
    "dojos.Dojo": {},
    "dojos.DojoMembership": {},
    "events.Event": {"exclude_fields": ["published_at", "announced_at"], "m2m_fields": ["team"]},
    "events.Registration": {},
    "events.TeamAttendance": {},
    "events.NinjaBelt": {},
    "events.NinjaBadge": {},
    "events.Badge": {},
    "events.Belt": {},
    "applications.Application": {},
    "applications.BackgroundCheckHistory": {},
    "mailing.MailPreference": {},
    "mailing.ConsentEvent": {},
    "mailing.EmailSuppression": {},
    "mailing.Campaign": {},
    "mailing.Journey": {},
    "mailing.Segment": {},
    "mailing.SegmentGroup": {},
    "mailing.SegmentRule": {},
    "mailing.EmailTemplate": {},
    "content.FAQ": {},
    "content.Testimonial": {},
    "content.Announcement": {},
    "content.OrganisationTeamMember": {},
    "content.Promotion": {},
    "content.Sponsor": {},
    "pathways.Pathway": {},
    "pathways.PathwayStep": {},
    "pathways.PathwayProject": {},
    "pathways.Skill": {},
    # The API (DATA_MODEL.md §13): who made, renewed or revoked a dojo's client.
    "api.DojoApiClient": {},
    "oauth2_provider.Application": {"mask_fields": ["client_secret"]},
    # Two-step login (DATA_MODEL.md §15): who turned it on or off, added or
    # removed a method, or reset someone's (the organisation, for a lost
    # phone); and the sign-in policy. Not what changes on every login.
    "accounts.SignInRequirement": {},
    "otp_totp.TOTPDevice": {
        "exclude_fields": [*_LOGIN_BOOKKEEPING, "drift", "last_t"],
        "mask_fields": ["key"],
    },
    "two_factor_webauthn.WebauthnDevice": {"exclude_fields": [*_LOGIN_BOOKKEEPING, "sign_count"]},
    "otp_static.StaticDevice": {"exclude_fields": _LOGIN_BOOKKEEPING},
}


def register_models():
    """Register `RECORDED` with auditlog (from CoreConfig.ready). Each model
    gets an explicit `include_fields` of its own columns: auditlog 3.4.1
    otherwise diffs a new row over every relation, reverse ones included."""
    from auditlog.registry import auditlog
    from django.apps import apps

    for label, options in RECORDED.items():
        model = apps.get_model(label)
        excluded = set(options.get("exclude_fields", ()))
        auditlog.register(
            model,
            include_fields=[f.name for f in model._meta.concrete_fields if f.name not in excluded],
            mask_fields=options.get("mask_fields"),
            m2m_fields=options.get("m2m_fields"),
        )


def mask(value):
    """AUDITLOG_MASK_CALLABLE: hide a masked field's value entirely
    (auditlog's default keeps half of it)."""
    return "***"


class AuditlogMiddleware(BaseAuditlogMiddleware):
    """No port either: AUDITLOG_DISABLE_REMOTE_ADDR leaves out the address
    but still reads X-Forwarded-Port. Every entry has its account; the
    infrastructure's logs have the rest."""

    @staticmethod
    def _get_remote_port(request):
        return None


def log_access(obj):
    """Record that the current request's account viewed `obj` (an ACCESS
    entry). Only for special-category data (a child's health notes, a
    criminal-record extract) and data handed out on request; `obj`'s model
    must be in `RECORDED`, or nothing is written."""
    accessed.send(sender=obj.__class__, instance=obj)


def without_audit_log(handle):
    """For a management command's `handle` that seeds demo data: seed data
    isn't history."""

    @wraps(handle)
    def wrapper(*args, **kwargs):
        with disable_auditlog():
            return handle(*args, **kwargs)

    return wrapper


class LogAccessAdminMixin:
    """For the ModelAdmin of a model holding special-category data: opening
    a row's change page in the Django admin is recorded as a view."""

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method == "GET":
            from django.contrib.admin.utils import unquote

            obj = self.get_object(request, unquote(object_id))
            if obj is not None:
                log_access(obj)
        return super().change_view(request, object_id, form_url, extra_context)


class AuditHistoryAdminMixin(AuditlogHistoryAdminMixin):
    """An "Audit log" column in the ModelAdmin's list, linking to a row's
    history. Only for accounts that may see the audit log
    (`auditlog.view_logentry`: the organisation's admin role, superusers):
    auditlog's own view only checks the view permission on the row's model,
    which the board has for dojos and sessions."""

    show_auditlog_history_link = True

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if not request.user.has_perm(AUDIT_LOG_PERMISSION):
            list_display = [name for name in list_display if name != "auditlog_link"]
        return list_display

    def auditlog_history_view(self, request, object_id, extra_context=None):
        from django.core.exceptions import PermissionDenied

        if not request.user.has_perm(AUDIT_LOG_PERMISSION):
            raise PermissionDenied
        return super().auditlog_history_view(request, object_id, extra_context)


# --- showing the log on the organisation dashboard (/manage/audit-log/) -------------

# What the dashboard shows instead of a value it hides.
HIDDEN = "****"
# Values longer than this are cut short on the dashboard.
DISPLAY_LENGTH = 120


def _hidden_categories():
    from privacy.registry import Category

    # Health, criminal records and secrets: the dashboard only says that
    # they changed (the Django admin's log shows what auditlog stored).
    return {Category.SPECIAL, Category.CRIMINAL, Category.SECURITY}


def is_hidden(model, field_name):
    """Whether the dashboard hides this field's values (as HIDDEN): a field
    the privacy registry classifies as health, criminal-record or security
    data, or one the log masks already. A model the registry doesn't know,
    or a field it has no decision about, is hidden too: when in doubt, hide.
    Not `export=False` as such: that also marks who did something (a
    reviewer, whoever ended an access), which is what the log is for."""
    from privacy.registry import site

    if model is None:
        return True
    if field_name in RECORDED.get(model._meta.label, {}).get("mask_fields", ()):
        return True
    entry = site.get(model) or site.get(model._meta.concrete_model)
    if entry is None:
        return True
    if field_name in entry.not_personal:
        return False
    privacy = entry.fields.get(field_name)
    return privacy is None or privacy.category in _hidden_categories()


def _shorten(value):
    value = str(value)
    return value if len(value) <= DISPLAY_LENGTH else value[:DISPLAY_LENGTH] + "…"


def _display_value(field, value):
    """One stored value (auditlog keeps them as strings) as a person reads it:
    a choice's label, a linked row's name, a date in Belgian notation."""
    from django.core.exceptions import ObjectDoesNotExist, ValidationError
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    if value in (None, "None", ""):
        return "—"
    if field is None:
        return _shorten(value)
    if getattr(field, "choices", None):
        return _shorten(dict(field.flatchoices).get(value, value))
    if field.many_to_one or field.one_to_one:
        try:
            return _shorten(field.related_model._base_manager.get(pk=field.related_model._meta.pk.to_python(value)))
        except (ObjectDoesNotExist, ValidationError, ValueError):
            return _shorten(value)
    if field.get_internal_type() == "DateTimeField":
        moment = parse_datetime(str(value))
        if moment is not None:
            if timezone.is_naive(moment):
                moment = timezone.make_aware(moment, datetime.UTC)
            return timezone.localtime(moment).strftime("%d/%m/%Y %H:%M")
    if field.get_internal_type() == "BooleanField":
        return {"True": "✓", "False": "✗"}.get(str(value), value)
    return _shorten(value)


def display_changes(entry):
    """An audit log entry's changes for the organisation dashboard: a list of
    {"field", "before", "after", "hidden"}, with every value `is_hidden`
    hides replaced by HIDDEN. A many-to-many change has no "before"; its
    "after" says what was added or removed."""
    from django.core.exceptions import FieldDoesNotExist

    model = entry.content_type.model_class() if entry.content_type_id else None
    rows = []
    for name, values in (entry.changes_dict or {}).items():
        field = None
        if model is not None:
            try:
                field = model._meta.get_field(name)
            except FieldDoesNotExist:
                pass
        label = str(getattr(field, "verbose_name", name))
        hidden = is_hidden(model, name)
        if isinstance(values, dict):  # {"type": "m2m", "operation": "add", "objects": [...]}
            after = HIDDEN if hidden else _shorten(", ".join(str(o) for o in values.get("objects", [])))
            rows.append({"field": label, "operation": values.get("operation", ""), "after": after, "hidden": hidden})
            continue
        before, after = (list(values) + [None, None])[:2]
        if hidden:
            before = after = HIDDEN
        else:
            before, after = _display_value(field, before), _display_value(field, after)
        rows.append({"field": label, "before": before, "after": after, "hidden": hidden})
    return rows
