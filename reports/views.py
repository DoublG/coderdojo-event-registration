"""The Reports area of the organisation dashboard (DATA_MODEL_REPORTS.md §30):
saved reports built with Perspective's viewer on a reporting dataset, and
the dataset's figures for it. The Reports area (`reports.view_report`)
opens the pages; making, changing and deleting a report take the model's
add/change/delete permissions (the admin role has all of them)."""

import csv
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.csp import CSP
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.csp import csp_override, csp_report_only_override
from django.views.decorators.http import require_POST

from accounts.organisation import Area, require_area
from core import caching

from .config import ConfigError, to_stored, to_viewer
from .datasets import DATASETS, get_dataset
from .datasets.base import DIMENSION
from .forms import ReportForm
from .models import Report

CACHE_SECONDS = 60 * 60
# report.js's URL carries a hash of its contents: the browser caches static
# files, and the vendored files it imports have their version in the path.
REPORT_JS_VERSION = hashlib.sha256(
    (Path(__file__).parent / "static" / "reports" / "report.js").read_bytes()
).hexdigest()[:10]


def _with_webassembly(policy):
    """The site's policy plus what Perspective needs: WebAssembly, and blob:
    for the glue code and workers its bundles start from blob: URLs (the
    viewer's WebAssembly glue, the engine's worker, the chart renderer's
    worker, which imports the glue again). blob: only lets a script that
    already runs start another, so it adds nothing an injected script needs."""
    policy = {**policy}
    policy["script-src"] = [*policy.get("script-src", []), CSP.WASM_UNSAFE_EVAL, "blob:"]
    policy["worker-src"] = [CSP.SELF, "blob:"]
    return policy


def perspective_policy(view):
    """Only the pages that load Perspective get WebAssembly: every other page
    keeps the site's policy (core.tests.SecurityHeadersTests)."""
    if getattr(settings, "SECURE_CSP", None):
        view = csp_override(_with_webassembly(settings.SECURE_CSP))(view)
    if getattr(settings, "SECURE_CSP_REPORT_ONLY", None):
        view = csp_report_only_override(_with_webassembly(settings.SECURE_CSP_REPORT_ONLY))(view)
    return view


def _require(request, action):
    if not request.user.has_perm(f"reports.{action}_report"):
        raise PermissionDenied


def figures(dataset, dojo=None):
    """The dataset's rows in the current language (all dojos, small groups
    merged; or one dojo's own, never merged), cached for an hour: one query
    per dataset, language and dojo, whatever number of reports use it."""
    language = get_language() or settings.LANGUAGE_CODE

    def build():
        table = dataset.table(dojo=dojo)
        return {
            "rows": dataset.labelled(table, dojo),
            "hidden": table.hidden,
            "as_of": timezone.localtime().strftime("%H:%M"),
        }

    # The labels in the key too: a deploy that changes or translates one gets
    # new figures at once, instead of an hour of reports that can't find it.
    labels = hashlib.sha256("|".join(str(column.label) for column in dataset.columns).encode()).hexdigest()[:12]
    scope = f"dojo-{dojo.pk}" if dojo else f"all-{settings.REPORT_MIN_GROUP}"
    return caching.cached(f"reports:{dataset.key}:{scope}:{language}:{labels}", build, CACHE_SECONDS, name="reports")


def csv_response(dataset, dojo=None):
    """The figures as a CSV file: what works without JavaScript, and what a
    screen reader or a spreadsheet can use."""
    rows = figures(dataset, dojo)["rows"]
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{dataset.key}.csv"'
    response.write("\ufeff")  # so a spreadsheet opens it as UTF-8
    writer = csv.writer(response)
    labels = [str(column.label) for column in dataset.columns_for(dojo)]
    writer.writerow(labels)
    for row in rows:
        writer.writerow([row[label] for label in labels])
    return response


def viewer_context(request, dataset, title, stored_config, editable, dojo=None):
    """What reports/partials/_viewer.html and report.js need."""
    viewer_config, missing = to_viewer(stored_config, dataset, dojo)
    found = figures(dataset, dojo)
    return {
        "dataset": dataset,
        "missing": missing,
        "hidden": found["hidden"],
        "as_of": found["as_of"],
        "min_group": settings.REPORT_MIN_GROUP,
        "setup": {
            "config": viewer_config,
            "title": title,
            "editable": editable,
            # The site's theme (the "theme" cookie the nav's switch sets; light by default).
            "dark": request.COOKIES.get("theme") == "dark",
            "schema": {
                str(column.label): "string" if column.kind == DIMENSION else "integer"
                for column in dataset.columns_for(dojo)
            },
            "messages": {"loadFailed": _("The report couldn't be loaded. Try again, or download the figures.")},
        },
        "language": (get_language() or "")[:2],
        "script_version": REPORT_JS_VERSION,
    }


@login_required
def report_list(request):
    require_area(request, Area.REPORTS)
    return render(
        request,
        "reports/report_list.html",
        {
            "reports": Report.objects.all(),
            "datasets": DATASETS.values(),
            "can_add": request.user.has_perm("reports.add_report"),
            "active": "reports",
        },
    )


@login_required
def report_data(request, dataset_key):
    """The figures Perspective loads, as JSON."""
    require_area(request, Area.REPORTS)
    return JsonResponse(figures(get_dataset(dataset_key)))


@login_required
def report_csv(request, dataset_key):
    require_area(request, Area.REPORTS)
    return csv_response(get_dataset(dataset_key))


def _viewer_page(request, dataset, report, form, config):
    can_edit = request.user.has_perm("reports.change_report" if report else "reports.add_report")
    title = report.label() if report else _("New report")
    return render(
        request,
        "reports/report_detail.html",
        {
            **viewer_context(request, dataset, title, config, can_edit),
            "report": report,
            "form": form,
            "can_edit": can_edit,
            "can_add": request.user.has_perm("reports.add_report"),
            "can_delete": report is not None and request.user.has_perm("reports.delete_report"),
            "data_url": reverse("manage_report_data", args=[dataset.key]),
            "csv_url": reverse("manage_report_csv", args=[dataset.key]),
            "active": "reports",
        },
    )


def _save(request, form, dataset, report):
    """Store the form's report; returns the saved report, or None with the
    error on the form."""
    try:
        config = to_stored(form.cleaned_data["config"], dataset)
    except ConfigError:
        form.add_error(None, _("The report's settings couldn't be read. Change something and save again."))
        return None
    report = report or Report(dataset=dataset.key, created_by=request.user)
    report.name = form.cleaned_data["name"]
    report.description = form.cleaned_data["description"]
    report.status = form.cleaned_data["status"]
    report.shared_with_dojos = bool(form.cleaned_data.get("shared_with_dojos")) and dataset.shareable
    report.position = form.cleaned_data["position"] or 0
    report.config = config
    report.updated_by = request.user
    report.save()
    return report


@login_required
@perspective_policy
def report_create(request, dataset_key):
    require_area(request, Area.REPORTS)
    _require(request, "add")
    dataset = get_dataset(dataset_key)
    form = ReportForm(request.POST or None, shareable=dataset.shareable)
    if request.method == "POST" and form.is_valid():
        report = _save(request, form, dataset, None)
        if report:
            messages.success(request, _("Report saved."))
            return redirect("manage_report_detail", report_id=report.id)
    return _viewer_page(request, dataset, None, form, {})


@login_required
@perspective_policy
def report_detail(request, report_id):
    require_area(request, Area.REPORTS)
    report = get_object_or_404(Report, pk=report_id)
    dataset = get_dataset(report.dataset)
    form = ReportForm(
        request.POST or None,
        shareable=dataset.shareable,
        initial={
            "name": report.name,
            "description": report.description,
            "status": report.status,
            "shared_with_dojos": report.shared_with_dojos,
            "position": report.position,
            "config": json.dumps(report.config),
        },
    )
    if request.method == "POST":
        as_new = "save_as_new" in request.POST
        _require(request, "add" if as_new else "change")
        if form.is_valid():
            saved = _save(request, form, dataset, None if as_new else report)
            if saved:
                messages.success(request, _("Saved as a new report.") if as_new else _("Report saved."))
                return redirect("manage_report_detail", report_id=saved.id)
    return _viewer_page(request, dataset, report, form, report.config)


@login_required
@require_POST
def report_delete(request, report_id):
    require_area(request, Area.REPORTS)
    _require(request, "delete")
    get_object_or_404(Report, pk=report_id).delete()
    messages.success(request, _("Report deleted."))
    return redirect("manage_report_list")
