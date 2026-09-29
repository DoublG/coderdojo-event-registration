"""The management area's landing (/manage/, DATA_MODEL.md §20): one entry
point for the organisation's dashboard and the dojos' admin areas, reached
from the nav's one *Manage* link. Each page behind it keeps its own access
check (accounts.organisation, dojos.access)."""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect

from accounts.organisation import Area
from accounts.sign_in import meets_requirement

from .manage_nav import request_manage_contexts

# Where each organisation area opens (accounts.organisation.Area).
AREA_LANDINGS = {
    Area.COMMUNICATION: "manage_campaign_list",
    Area.VOLUNTEERS: "manage_check_list",
    Area.PUBLIC_SITE: "manage_promotion_list",
    Area.NINJAS: "manage_badge_list",
    Area.PRIVACY: "manage_privacy",
    Area.SECURITY: "manage_security",
}


@login_required
def manage_home(request):
    """The first organisation area the account may open (campaigns for an
    organisation admin, background checks for a reviewer), else the first
    dojo it manages; a 404 for anyone with neither (same
    no-leak reasoning as dojos.access), or whose login is below the
    organisation's sign-in policy."""
    contexts = request_manage_contexts(request)
    if not contexts.any or not meets_requirement(request):
        raise Http404
    if contexts.areas:
        return redirect(AREA_LANDINGS[contexts.areas[0]])
    return redirect("dojo_dashboard", dojo_id=contexts.first_dojo.id)
