def user_roles(request):
    """Exposes which role-specific profile (if any) the logged-in user has,
    so the shared nav (core/templates/core/menu.html) can show the right
    account links without every view needing to compute this itself. A user
    can hold more than one of these at once (Django multi-table inheritance
    doesn't prevent it — see accounts.provisioning.attach_role), so these are
    independent checks, not a single role lookup."""
    dojo_owner, guardian, helper = None, None, None
    if request.user.is_authenticated:
        dojo_owner = getattr(request.user, "dojoowner", None)
        guardian = getattr(request.user, "guardian", None)
        helper = getattr(request.user, "helperaccount", None)
    return {"user_dojo_owner": dojo_owner, "user_guardian": guardian, "user_helper": helper}
