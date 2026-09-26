"""The audit log (django-auditlog, DATA_MODEL.md §14): who changed what, and
who viewed the most sensitive data. The recorded models are `RECORDED`
below (every other model is listed with its reason in
core.tests.AuditLogCoverageTests); the actor comes from `AuditlogMiddleware`.
It's shown only in the Django admin, read-only, to the organisation's admin
role."""

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
RECORDED = {
    "accounts.User": {**USER_OPTIONS, "m2m_fields": ["groups", "user_permissions"]},
    # The Background checks admin saves through this proxy of User.
    "applications.BackgroundCheck": USER_OPTIONS,
    # Health data (GDPR art. 9).
    "accounts.Ninja": {"mask_fields": ["allergies_notes"]},
    "accounts.Guardianship": {},
    "accounts.OrganisationRole": {},
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
