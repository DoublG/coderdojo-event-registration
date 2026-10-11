"""The reports the organisation shares with dojos, in a dojo's admin area
(DATA_MODEL_REPORTS.md §30): every published report shared with the dojos,
for the dojo's champion only (dojos.access.VIEW_REPORTS), read-only and on
the dojo's own figures. The dojo filter is in the dataset's query
(Dataset.query_rows(dojo)), so another dojo's figures never reach the page,
whatever someone does in the viewer; a dojo's own figures aren't merged."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from dojos.access import VIEW_REPORTS, require_dojo_access
from dojos.views import _admin_context

from .datasets import DATASETS, get_dataset
from .models import Report
from .views import csv_response, figures, perspective_policy, viewer_context


def shared_reports():
    """The reports every dojo's champion sees, in their order."""
    shareable = [key for key, dataset in DATASETS.items() if dataset.shareable]
    return Report.objects.filter(status=Report.PUBLISHED, shared_with_dojos=True, dataset__in=shareable)


def _shareable_dataset(dataset_key):
    dataset = get_dataset(dataset_key)
    if not dataset.shareable:
        raise Http404
    return dataset


@login_required
def dojo_report_list(request, dojo_id):
    access = require_dojo_access(request, dojo_id, VIEW_REPORTS)
    return render(
        request,
        "reports/dojo/report_list.html",
        {**_admin_context(request, access), "reports": shared_reports(), "active": "reports"},
    )


@login_required
@perspective_policy
def dojo_report_detail(request, dojo_id, report_id):
    access = require_dojo_access(request, dojo_id, VIEW_REPORTS)
    report = get_object_or_404(shared_reports(), pk=report_id)
    dataset = get_dataset(report.dataset)
    dojo = access.dojo
    return render(
        request,
        "reports/dojo/report_detail.html",
        {
            **_admin_context(request, access),
            **viewer_context(request, dataset, report.label(), report.config, editable=False, dojo=dojo),
            "report": report,
            "data_url": reverse("dojo_report_data", kwargs={"dojo_id": dojo.id, "dataset_key": dataset.key}),
            "csv_url": reverse("dojo_report_csv", kwargs={"dojo_id": dojo.id, "dataset_key": dataset.key}),
            "active": "reports",
        },
    )


@login_required
def dojo_report_data(request, dojo_id, dataset_key):
    access = require_dojo_access(request, dojo_id, VIEW_REPORTS)
    return JsonResponse(figures(_shareable_dataset(dataset_key), access.dojo))


@login_required
def dojo_report_csv(request, dojo_id, dataset_key):
    access = require_dojo_access(request, dojo_id, VIEW_REPORTS)
    return csv_response(_shareable_dataset(dataset_key), access.dojo)
