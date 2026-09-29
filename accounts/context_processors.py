def user_roles(request):
    """Exposes, for the shared nav (core/templates/core/menu.html) and the
    account page, where the logged-in account stands as a volunteer —
    without every view recomputing it: whether it's an approved champion
    and/or mentor (applications.services), and the first dojo whose admin
    area it can open (dojos.access); whether it holds an organisation role
    (accounts.organisation); and whether the nav's one "Manage" link, to
    the management area (/manage/, core.manage_nav), applies: an
    organisation admin, a background-check reviewer or a dojo's
    champion/mentor. The board's role gets its "Organisation" link to the
    Django admin."""
    from applications.services import is_approved_champion, is_approved_mentor
    from dojos.access import accessible_dojos

    from .organisation import is_reviewer

    approved_champion = approved_mentor = False
    applied_kinds = set()
    admin_dojo = None
    organisation_role = organisation_admin = organisation_board = reviewer = False
    if request.user.is_authenticated and not request.user.is_ninja:
        approved_champion = is_approved_champion(request.user)
        approved_mentor = is_approved_mentor(request.user)
        # Kinds with a pending or approved application — no point offering
        # "Apply ..." for those again.
        applied_kinds = set(request.user.applications.exclude(status="rejected").values_list("kind", flat=True))
        admin_dojo = accessible_dojos(request.user).first()
        roles = set(request.user.organisation_roles.values_list("role", flat=True))
        organisation_role = bool(roles)
        organisation_admin = "admin" in roles
        organisation_board = "board" in roles
        reviewer = is_reviewer(request.user)
    return {
        "user_is_approved_champion": approved_champion,
        "user_is_approved_mentor": approved_mentor,
        "user_applied_champion": "champion" in applied_kinds,
        "user_applied_mentor": "mentor" in applied_kinds,
        "user_admin_dojo": admin_dojo,
        "user_has_organisation_role": organisation_role,
        "user_is_organisation_admin": organisation_admin,
        "user_is_organisation_board": organisation_board,
        "user_can_manage": admin_dojo is not None or organisation_admin or reviewer,
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
