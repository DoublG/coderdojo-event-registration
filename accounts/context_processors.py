def user_roles(request):
    """Exposes which role-specific profile (if any) the logged-in user has,
    so the shared nav (core/templates/core/menu.html) can show the right
    account links without every view needing to compute this itself. A user
    can hold more than one of these at once (Django multi-table inheritance
    doesn't prevent it — see accounts.provisioning.attach_role), so these are
    independent checks, not a single role lookup."""
    from dojos.access import accessible_dojos

    dojo_owner, helper, admin_dojo = None, None, None
    if request.user.is_authenticated:
        dojo_owner = getattr(request.user, "dojoowner", None)
        helper = getattr(request.user, "helperaccount", None)
        if dojo_owner is not None or helper is not None:
            # First dojo whose admin area they can open (owner or helper —
            # see dojos.access), for the nav's "Manage" link.
            admin_dojo = accessible_dojos(request.user).first()
    return {
        "user_dojo_owner": dojo_owner, "user_helper": helper,
        "user_admin_dojo": admin_dojo,
    }
