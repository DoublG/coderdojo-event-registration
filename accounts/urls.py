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
    path("register/guardian/link/", views.link_guardian_role, name="link_guardian_role"),
    path("guardian/<int:guardian_id>/", views.guardian_detail, name="guardian_detail"),
    path("guardian/<int:guardian_id>/child/add/", views.add_child, name="add_child"),
    path("guardian/<int:guardian_id>/child/<int:child_id>/", views.child_detail, name="child_detail"),
    path("guardian/<int:guardian_id>/child/<int:child_id>/edit/", views.edit_child, name="edit_child"),
    path("guardian/<int:guardian_id>/child/<int:child_id>/awards/", views.award_widget, name="award_widget"),
    path(
        "guardian/<int:guardian_id>/registration/<int:registration_id>/cancel/",
        views.cancel_registration,
        name="cancel_registration",
    ),
]
