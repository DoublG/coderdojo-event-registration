"""Two-step login on an account (DATA_MODEL.md §15): its sign-in methods and
backup codes. Every change goes through here, never straight to the device
models, so the security mails go out and the login keeps working.

The devices are django-otp's: an authenticator app (`TOTPDevice`, at most
one), passkeys (`WebauthnDevice`, django-two-factor-auth's plugin, any
number) and backup codes (one `StaticDevice` holding single-use
`StaticToken`s). Two-step login is on while the account has an app or a
passkey; the backup codes only exist alongside them.

django-two-factor-auth's login asks for the device named "default" first and
offers the others as alternatives, so exactly one app or passkey carries
that name (`_ensure_default`), whichever was added first.
"""

import django_otp
from django.db import transaction
from django.dispatch import receiver
from django.utils.translation import gettext as _
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from two_factor.plugins.webauthn.models import WebauthnDevice
from two_factor.signals import user_verified

from .security_mail import send_security_mail

APP = "app"
PASSKEY = "passkey"
BACKUP_CODE_COUNT = 10
DEFAULT_NAME = "default"
BACKUP_NAME = "backup"


class TwoStepError(Exception):
    """A change that isn't allowed, with a message for the person."""


def app_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=True).first()


def passkeys(user):
    return WebauthnDevice.objects.filter(user=user, confirmed=True).order_by("created_at", "id")


def methods(user):
    """Every app and passkey on the account, oldest first."""
    devices = list(TOTPDevice.objects.filter(user=user, confirmed=True)) + list(passkeys(user))
    return sorted(devices, key=lambda device: (device.created_at, device.pk))


def is_on(user):
    return (
        TOTPDevice.objects.filter(user=user, confirmed=True).exists()
        or WebauthnDevice.objects.filter(user=user, confirmed=True).exists()
    )


def has_passkey(user):
    return WebauthnDevice.objects.filter(user=user, confirmed=True).exists()


def kind_of(device):
    return PASSKEY if isinstance(device, WebauthnDevice) else APP


def backup_codes_left(user):
    return StaticToken.objects.filter(device__user=user).count()


def make_backup_codes(user):
    """A fresh set of backup codes, replacing any earlier ones; returned once,
    to show the person (they're kept as plain single-use tokens)."""
    device, _created = StaticDevice.objects.get_or_create(user=user, name=BACKUP_NAME)
    with transaction.atomic():
        device.token_set.all().delete()
        codes = [StaticToken.random_token() for _i in range(BACKUP_CODE_COUNT)]
        StaticToken.objects.bulk_create([StaticToken(device=device, token=code) for code in codes])
    return codes


def _ensure_default(user):
    current = methods(user)
    if current and not any(device.name == DEFAULT_NAME for device in current):
        first = current[0]
        first.name = DEFAULT_NAME
        first.save(update_fields=["name"])


def _added(request, device):
    """After `device` is saved: it counts for this session (the person just
    proved they have it), and they get a mail."""
    user = request.user
    was_on = len(methods(user)) > 1  # `device` is already one of them
    device.name = DEFAULT_NAME if not was_on else kind_of(device)
    device.save(update_fields=["name"])
    django_otp.login(request, device)
    _mail(user, "two_step_method_added" if was_on else "two_step_turned_on", method=kind_of(device))
    return device


def add_app(request, form):
    """Save the authenticator app a validated two_factor TOTPDeviceForm checked."""
    if app_device(request.user):
        raise TwoStepError(_("This account already has an authenticator app. Remove it first to use another."))
    return _added(request, form.save())


def add_passkey(request, setup_data):
    """Save the passkey a validated WebAuthn registration describes (the
    cleaned data of two_factor's WebauthnDeviceValidationForm). Raises
    TwoStepError when the browser's answer doesn't check out."""
    from two_factor.plugins.registry import registry
    from webauthn.helpers.exceptions import WebAuthnException

    method = registry.get_method("webauthn")
    try:
        device = method.get_device_from_setup_data(request, {"webauthn": setup_data})
    except WebAuthnException as exc:
        raise TwoStepError(_("That passkey couldn't be checked. Please try again.")) from exc
    device.confirmed = True
    device.save()
    return _added(request, device)


def requirement_blocks_removal(user, device=None):
    """The message why removing `device` (None: every method) would leave the
    account below what its role requires, or None."""
    from .sign_in import PASSKEY as PASSKEY_LEVEL
    from .sign_in import PASSWORD, requirements_for

    enforced, _upcoming = requirements_for(user)
    if enforced.level == PASSWORD:
        return None
    left = [other for other in methods(user) if device is not None and other != device]
    if enforced.level == PASSKEY_LEVEL:
        left = [other for other in left if kind_of(other) == PASSKEY]
    if left:
        return None
    if device is None:
        return _("Your role needs two-step login, so you can't turn it off.")
    if enforced.level == PASSKEY_LEVEL:
        return _("Your role needs a passkey, so you can't remove your last one. Add another passkey first.")
    return _("Your role needs two-step login, so you can't remove your last sign-in method. Add another one first.")


def remove(user, device):
    """Remove one app or passkey. Removing the last one turns two-step login
    off (and drops the backup codes)."""
    if device.user_id != user.pk:
        raise TwoStepError(_("That sign-in method isn't on your account."))
    if message := requirement_blocks_removal(user, device):
        raise TwoStepError(message)
    kind = kind_of(device)
    with transaction.atomic():
        device.delete()
        if is_on(user):
            _ensure_default(user)
        else:
            StaticDevice.objects.filter(user=user).delete()
    if is_on(user):
        _mail(user, "two_step_method_removed", method=kind)
    else:
        _mail(user, "two_step_turned_off", by_organisation=False)


def turn_off(user, by_organisation=False):
    """Remove every app, passkey and backup code. The person checks this
    themselves (their password, and their role's requirement); the
    organisation uses it for someone who lost their phone
    (by_organisation=True: their role may require it again at the next login)."""
    if not by_organisation and (message := requirement_blocks_removal(user)):
        raise TwoStepError(message)
    if not is_on(user) and not StaticDevice.objects.filter(user=user).exists():
        return
    with transaction.atomic():
        TOTPDevice.objects.filter(user=user).delete()
        WebauthnDevice.objects.filter(user=user).delete()
        StaticDevice.objects.filter(user=user).delete()
    _mail(user, "two_step_turned_off", by_organisation=by_organisation)


def _mail(user, key, **context):
    """The security mail to the account (and, for a child's own login, a
    notice to its guardians: accounts.security_mail)."""
    send_security_mail(user, key, **context)


@receiver(user_verified)
def _backup_code_used(sender, request, user, device, **kwargs):
    """A login with a backup code: tell the person, so a stolen code shows."""
    if isinstance(device, StaticDevice):
        _mail(user, "backup_code_used", codes_left=backup_codes_left(user))
