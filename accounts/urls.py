from django.urls import include, path
from django.views.generic import RedirectView

from . import manage, people, security_views, views

# django-two-factor-auth reverses a few names in its own namespace; they point
# at our pages (accounts.security_views), never at the package's views.
_two_factor = (
    [
        path("account/security/setup/", RedirectView.as_view(pattern_name="account_security"), name="setup"),
        path("account/security/webauthn/", include("two_factor.plugins.webauthn.urls", namespace="webauthn")),
    ],
    "two_factor",
)

urlpatterns = [
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("change-password/", views.change_password, name="change_password"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("password-reset/complete/", views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("register/", views.register, name="register"),
    path("register/guardian/", views.register_guardian, name="register_guardian"),
    path("account/", views.account_home, name="account_home"),
    path("account/security/", security_views.security, name="account_security"),
    path("account/security/app/", security_views.security_app, name="account_security_app"),
    path("account/security/passkey/", security_views.security_passkey, name="account_security_passkey"),
    path("account/security/backup-codes/", security_views.security_backup_codes, name="account_security_backup_codes"),
    path(
        "account/security/remove/<str:kind>/<int:device_id>/",
        security_views.security_remove,
        name="account_security_remove",
    ),
    path("account/security/turn-off/", security_views.security_turn_off, name="account_security_turn_off"),
    path(
        "account/security/forget-browser/",
        security_views.security_forget_browser,
        name="account_security_forget_browser",
    ),
    path("", include(_two_factor)),
    path("manage/security/", manage.security_policy, name="manage_security"),
    path("manage/django-admin/", manage.manage_admin_access, name="manage_admin_access"),
    path("manage/django-admin/end/", manage.manage_admin_access_end, name="manage_admin_access_end"),
    path("manage/people/", people.manage_people, name="manage_people"),
    path("manage/people/add/", people.manage_people_add, name="manage_people_add"),
    path("manage/people/roles/", people.manage_people_roles, name="manage_people_roles"),
    path("manage/people/<int:user_id>/", people.manage_person, name="manage_person"),
    path("manage/people/access/<int:grant_id>/end/", people.manage_people_end_access, name="manage_people_end_access"),
    path(
        "manage/people/invitations/<int:invitation_id>/resend/",
        people.manage_invitation_resend,
        name="manage_invitation_resend",
    ),
    path(
        "manage/people/invitations/<int:invitation_id>/withdraw/",
        people.manage_invitation_withdraw,
        name="manage_invitation_withdraw",
    ),
    path("invitation/<str:token>/", people.organisation_invitation, name="organisation_invitation"),
    path(
        "invitation/<str:token>/sign-up/",
        people.organisation_invitation_sign_up,
        name="organisation_invitation_sign_up",
    ),
    path(
        "manage/security/accounts/<int:user_id>/turn-off/", manage.turn_off_two_step, name="manage_security_turn_off"
    ),
    path("account/edit/", views.edit_account, name="edit_account"),
    path("account/email/", views.change_email, name="change_email"),
    path("account/email/confirm/<str:token>/", views.confirm_email_change, name="confirm_email_change"),
    path("account/ninja/add/", views.add_ninja, name="add_ninja"),
    path("account/ninja/<int:ninja_id>/", views.ninja_detail, name="ninja_detail"),
    path("account/ninja/<int:ninja_id>/edit/", views.edit_ninja, name="edit_ninja"),
    path("account/ninja/<int:ninja_id>/avatar/", views.ninja_avatar, name="ninja_avatar"),
    path("account/ninja/<int:ninja_id>/badges/", views.ninja_badges, name="ninja_badges"),
    path("account/ninja/<int:ninja_id>/login/", views.ninja_login_create, name="ninja_login_create"),
    path("account/ninja/<int:ninja_id>/login/resend/", views.ninja_login_resend, name="ninja_login_resend"),
    path("account/ninja/<int:ninja_id>/login/remove/", views.ninja_login_remove, name="ninja_login_remove"),
    path(
        "account/registration/<int:registration_id>/cancel/",
        views.cancel_registration,
        name="cancel_registration",
    ),
]
