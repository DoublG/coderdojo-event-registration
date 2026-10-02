"""The accounts app's pages, by area: logging in and passwords (auth), family
sign-up (signup), the account page and its details (family), a child's pages
(children) and a child's own login (child_logins), with what they share
(common). The Sign-in security pages are accounts.security_views. Every view
is importable from here, as urls.py does."""

from .auth import (  # noqa: F401
    LoginLinkView,
    LoginView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
    _post_login_redirect,
    change_password,
    login,
    login_link,
    login_link_reauth,
    login_link_request,
    logout,
)
from .child_logins import (  # noqa: F401
    _guardian_login_action,
    _login_card,
    _login_card_context,
    ninja_login_create,
    ninja_login_email,
    ninja_login_remove,
    ninja_login_resend,
    ninja_login_two_step_off,
    ninja_login_use_password,
)
from .children import (  # noqa: F401
    _badges_queryset,
    _set_icon,
    add_ninja,
    edit_ninja,
    ninja_avatar,
    ninja_badges,
    ninja_detail,
)
from .common import (  # noqa: F401
    BADGES_PAGE_SIZE,
    _get_own_ninja,
    _site_language,
)
from .family import (  # noqa: F401
    _children_context,
    _render_account_home,
    account_home,
    cancel_registration,
    change_email,
    confirm_email_change,
    edit_account,
)
from .signup import (  # noqa: F401
    _create_ninjas,
    register,
    register_guardian,
)
