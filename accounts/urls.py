from django.urls import path

from . import views

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
    path("account/ninja/add/", views.add_ninja, name="add_ninja"),
    path("account/ninja/<int:ninja_id>/", views.ninja_detail, name="ninja_detail"),
    path("account/ninja/<int:ninja_id>/edit/", views.edit_ninja, name="edit_ninja"),
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
