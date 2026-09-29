import tempfile
from pathlib import Path


class TempMediaMixin:
    """Stores any file a test saves in a throwaway MEDIA_ROOT instead of the
    real media/ directory."""

    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = self.settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.media_root = Path(media.name)


def login_data(username, password):
    """The POST of the login's first step (accounts.views.LoginView, a
    django-two-factor-auth wizard: step name plus prefixed fields)."""
    return {"login_view-current_step": "auth", "auth-username": username, "auth-password": password}


def token_data(token, step="token", view="login_view"):
    """The POST of the login's second step: a code, a backup code
    (step="backup") or a passkey's answer. `view="login_link_view"` for a
    login from an emailed link."""
    return {f"{view}-current_step": step, f"{step}-otp_token": token}


def link_login_data():
    """The POST of a login link's first step ("Log in as ...?",
    accounts.views.LoginLinkView): no fields, the link is the proof."""
    return {"login_link_view-current_step": "auth"}


def totp_code(device):
    """The code `device` (a django-otp TOTPDevice) shows right now."""
    from django_otp.oath import totp

    return str(totp(device.bin_key, device.step, device.t0, device.digits, device.drift)).zfill(device.digits)


def login_verified(client, user):
    """Log `user` in with two-step login passed, as after a code: gives the
    account an authenticator app when it has none. For tests of what an
    account whose role needs two-step login may do (accounts.sign_in)."""
    from django_otp import DEVICE_ID_SESSION_KEY
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if device is None:
        device = TOTPDevice.objects.create(user=user, name="default")
    client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    return device


def with_admin_access(user, reason="Fixing a registration"):
    """Open `user`'s time-boxed access to the Django admin (accounts.admin_access,
    DATA_MODEL.md §23), as asked for on the dashboard; returns the account
    fresh (staff status and permission cache). It needs an organisation role."""
    from accounts.admin_access import request_access

    request_access(user, reason)
    return type(user).objects.get(pk=user.pk)
