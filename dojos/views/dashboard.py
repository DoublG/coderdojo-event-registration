"""The dashboard (`/dojos/<id>/dashboard/`): the overview a dojo's team lands
on, built by dojos.dashboard."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .. import dashboard
from ..access import require_dojo_access
from .common import _admin_context


@login_required
def dojo_dashboard(request, dojo_id):
    access = require_dojo_access(request, dojo_id)
    return render(
        request,
        "dojos/dojo_dashboard.html",
        {
            "overview": dashboard.build(access),
            "active": "dashboard",
            **_admin_context(request, access),
        },
    )
