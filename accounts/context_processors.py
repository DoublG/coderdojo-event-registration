def user_roles(request):
    """Exposes, for the shared nav (core/templates/core/menu.html) and the
    account page, where the logged-in account stands as a volunteer —
    without every view recomputing it: whether it's an approved champion
    and/or mentor (applications.services), and the first dojo whose admin
    area it can open (dojos.access); whether it holds an organisation role
    (accounts.organisation); and whether the nav's one "Manage" link, to
    the management area (/manage/, core.manage_nav), applies: an account
    that may open an organisation dashboard area (accounts.organisation,
    e.g. an organisation admin or a background-check reviewer) or a dojo's
    champion/mentor, or any organisation role (the board too: its page to
    ask for the Django admin, DATA_MODEL.md §23)."""
    from .navigation import for_request

    approved_champion = approved_mentor = False
    applied_kinds = frozenset()
    admin_dojo = None
    organisation_role = organisation_admin = has_areas = False
    if request.user.is_authenticated and not request.user.is_ninja:
        # Cached per account (accounts.navigation): only for showing links.
        navigation = for_request(request)
        approved_champion = navigation.approved_champion
        approved_mentor = navigation.approved_mentor
        # Kinds with a pending or approved application — no point offering
        # "Apply ..." for those again.
        applied_kinds = navigation.applied_kinds
        admin_dojo = navigation.admin_dojo
        organisation_role = bool(navigation.organisation_roles)
        organisation_admin = "admin" in navigation.organisation_roles
        has_areas = bool(navigation.areas)
    return {
        "user_is_approved_champion": approved_champion,
        "user_is_approved_mentor": approved_mentor,
        "user_applied_champion": "champion" in applied_kinds,
        "user_applied_mentor": "mentor" in applied_kinds,
        "user_admin_dojo": admin_dojo,
        "user_has_organisation_role": organisation_role,
        "user_is_organisation_admin": organisation_admin,
        "user_can_manage": admin_dojo is not None or has_areas or organisation_role,
    }


def sign_in_notice(request):
    """`sign_in_notice`, for the notice in the page shells
    (accounts/partials/_sign_in_notice.html): the stronger login the account's
    role will need from a later day (accounts.sign_in), while the account
    doesn't have it yet; otherwise None. Lazy: worked out only on a page that
    shows it, once per request."""
    from functools import cache

    @cache
    def notice():
        from . import sign_in, two_step

        user = request.user
        if not user.is_authenticated or user.account_type != "adult":
            return None
        _enforced, upcoming = sign_in.requirements_for(user)
        if upcoming is None:
            return None
        has = two_step.has_passkey(user) if upcoming.level == sign_in.PASSKEY else two_step.is_on(user)
        return None if has else upcoming

    return {"sign_in_notice": notice}
