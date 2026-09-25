def user_roles(request):
    """Exposes, for the shared nav (core/templates/core/menu.html) and the
    account page, where the logged-in account stands as a volunteer —
    without every view recomputing it: whether it's an approved champion
    and/or mentor (applications.services), and the first dojo whose admin
    area it can open (dojos.access), for the "Manage" link; and whether it
    holds an organisation role (accounts.organisation), for the
    "Organisation" link."""
    from applications.services import is_approved_champion, is_approved_mentor
    from dojos.access import accessible_dojos

    approved_champion = approved_mentor = False
    applied_kinds = set()
    admin_dojo = None
    organisation_role = False
    organisation_admin = False
    if request.user.is_authenticated and not request.user.is_ninja:
        approved_champion = is_approved_champion(request.user)
        approved_mentor = is_approved_mentor(request.user)
        # Kinds with a pending or approved application — no point offering
        # "Apply ..." for those again.
        applied_kinds = set(
            request.user.applications.exclude(status="rejected").values_list("kind", flat=True)
        )
        admin_dojo = accessible_dojos(request.user).first()
        organisation_role = request.user.organisation_roles.exists()
        organisation_admin = request.user.organisation_roles.filter(role="admin").exists()
    return {
        "user_is_approved_champion": approved_champion,
        "user_is_approved_mentor": approved_mentor,
        "user_applied_champion": "champion" in applied_kinds,
        "user_applied_mentor": "mentor" in applied_kinds,
        "user_admin_dojo": admin_dojo,
        "user_has_organisation_role": organisation_role,
        "user_is_organisation_admin": organisation_admin,
    }
