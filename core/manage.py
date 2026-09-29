"""The management area's landing (/manage/, DATA_MODEL.md §20): one entry
point for the organisation's dashboard and the dojos' admin areas, reached
from the nav's one *Manage* link. Each page behind it keeps its own access
check (accounts.organisation, dojos.access)."""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect

from accounts.sign_in import meets_requirement

from .manage_nav import request_manage_contexts


@login_required
def manage_home(request):
    """The organisation's dashboard for an organisation admin (its
    background checks for a reviewer), else the first dojo the account
    manages; a 404 for anyone with neither (same
    no-leak reasoning as dojos.access), or whose login is below the
    organisation's sign-in policy."""
    contexts = request_manage_contexts(request)
    if not contexts.any or not meets_requirement(request):
        raise Http404
    if contexts.organisation_admin:
        return redirect("manage_campaign_list")
    if contexts.reviewer:
        return redirect("manage_check_list")
    return redirect("dojo_dashboard", dojo_id=contexts.first_dojo.id)
