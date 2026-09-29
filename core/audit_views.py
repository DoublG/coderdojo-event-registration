"""The audit log on the organisation dashboard (/manage/audit-log/, the Audit
log area, DATA_MODEL.md §14): read-only, with health, criminal-record and
security data hidden (core.audit.is_hidden). The Django admin keeps its own
read-only log page."""

from auditlog.models import LogEntry
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_safe

from accounts.organisation import Area, require_area

from .audit import RECORDED, display_changes

PAGE_SIZE = 50
ACTIONS = [
    (LogEntry.Action.CREATE, _("Created")),
    (LogEntry.Action.UPDATE, _("Changed")),
    (LogEntry.Action.DELETE, _("Deleted")),
    (LogEntry.Action.ACCESS, _("Viewed")),
]


def _recorded_types():
    """The recorded models, as (content type id, name) for the filter."""
    from django.apps import apps

    types = ContentType.objects.get_for_models(
        *(apps.get_model(label) for label in RECORDED), for_concrete_models=False
    )
    return sorted(
        ((ct.pk, str(model._meta.verbose_name).capitalize()) for model, ct in types.items()), key=lambda t: t[1]
    )


def _type_label(entry):
    model = entry.content_type.model_class() if entry.content_type_id else None
    return str(model._meta.verbose_name).capitalize() if model else entry.content_type.model


@login_required
@require_safe
def manage_audit_log(request):
    """Who changed what, newest first, filtered by a person or row's name,
    the kind of change and the kind of data."""
    require_area(request, Area.AUDIT_LOG)
    entries = LogEntry.objects.select_related("content_type", "actor").order_by("-timestamp", "-pk")
    query = request.GET.get("q", "").strip()
    if query:
        entries = entries.filter(
            Q(object_repr__icontains=query)
            | Q(actor__username__icontains=query)
            | Q(actor__email__icontains=query)
            | Q(actor__first_name__icontains=query)
            | Q(actor__last_name__icontains=query)
        )
    action = request.GET.get("action", "")
    if action.isdigit() and int(action) in dict(ACTIONS):
        entries = entries.filter(action=int(action))
    else:
        action = ""
    types = _recorded_types()
    kind = request.GET.get("type", "")
    if kind.isdigit() and int(kind) in dict(types):
        entries = entries.filter(content_type_id=int(kind))
    else:
        kind = ""

    page = Paginator(entries, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "core/manage_audit_log.html",
        {
            "active": "audit_log",
            "rows": [(entry, _type_label(entry), display_changes(entry)) for entry in page.object_list],
            "page": page,
            "filter_query": params.urlencode(),
            "query": query,
            "action": action,
            "actions": ACTIONS,
            "type": kind,
            "types": types,
        },
    )
