def user_roles(request):
    """Exposes which role-specific profile (if any) the logged-in user has,
    so the shared nav (core/templates/core/menu.html) can show the right
    account links without every view needing to compute this itself."""
    dojo_owner, guardian = None, None
    if request.user.is_authenticated:
        dojo_owner = getattr(request.user, "dojoowner", None)
        guardian = getattr(request.user, "guardian", None)
    return {"user_dojo_owner": dojo_owner, "user_guardian": guardian}
