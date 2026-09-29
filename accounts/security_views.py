"""The account's Sign-in security page (/account/security/, DATA_MODEL.md
§15): two-step login with an authenticator app, passkeys and backup codes.
Changes go through accounts/two_step.py and accounts/login_links.py. Every
person's login has it, an adult's or a ninja's own (DATA_MODEL.md §24), and
an account with two-step login on only changes it from a session that
passed it."""

from base64 import b32encode
from binascii import unhexlify
from io import BytesIO

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.util import random_hex
from two_factor.plugins.webauthn.models import WebauthnDevice
from two_factor.utils import get_otpauth_url
from two_factor.views.core import REMEMBER_COOKIE_PREFIX

from . import login_links, sign_in, two_step
from .forms import ConfirmIdentityForm, LinkToPasswordForm
from .models import User
from .two_step_forms import AppSetupForm, PasskeySetupForm

APP_KEY_SESSION = "two_step_app_key"
NEW_CODES_SESSION = "two_step_new_backup_codes"


def _own_account(request):
    """404 for the API's technical accounts: every person's login, an adult's
    or a ninja's own, has the same options (DATA_MODEL.md §24)."""
    if request.user.account_type not in (User.ADULT, User.NINJA):
        raise Http404


def _unverified(request):
    """An account with two-step login on whose session didn't pass it (an
    older login): it logs in again before changing anything."""
    is_verified = getattr(request.user, "is_verified", None)
    if two_step.is_on(request.user) and not (is_verified and is_verified()):
        auth_logout(request)
        messages.info(request, _("Please log in again, with your second step, to change how you sign in."))
        return redirect(f"{reverse('login')}?next={reverse('account_security')}")
    return None


def _after_first_method(request, was_on):
    """After adding a method: the first one comes with backup codes."""
    if not was_on:
        request.session[NEW_CODES_SESSION] = two_step.make_backup_codes(request.user)
        return redirect("account_security_backup_codes")
    return redirect("account_security")


@never_cache
@login_required
def security(request):
    _own_account(request)
    user = request.user
    enforced, upcoming = sign_in.requirements_for(user)
    methods = two_step.methods(user)
    return render(
        request,
        "accounts/security.html",
        {
            "app": next((device for device in methods if two_step.kind_of(device) == two_step.APP), None),
            "passkeys": [device for device in methods if two_step.kind_of(device) == two_step.PASSKEY],
            "is_on": bool(methods),
            "backup_codes_left": two_step.backup_codes_left(user),
            "enforced": enforced if enforced.level != sign_in.PASSWORD else None,
            "upcoming": upcoming,
            "status": sign_in.request_status(request),
            "remembered": any(key.startswith(REMEMBER_COOKIE_PREFIX) for key in request.COOKIES),
            "uses_link": user.uses_login_link,
        },
    )


def _qr_svg(url):
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    # Drop the XML declaration: the SVG goes inline in the page.
    return buffer.getvalue().decode("utf-8").split("?>", 1)[-1]


@never_cache
@login_required
def security_app(request):
    """Add an authenticator app: scan the QR code (or type the key), then
    enter the first code it shows."""
    _own_account(request)
    if response := _unverified(request):
        return response
    if two_step.app_device(request.user):
        messages.info(request, _("This account already has an authenticator app."))
        return redirect("account_security")
    key = request.session.get(APP_KEY_SESSION) or random_hex(20)
    request.session[APP_KEY_SESSION] = key
    form = AppSetupForm(key=key, user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        was_on = two_step.is_on(request.user)
        try:
            two_step.add_app(request, form)
        except two_step.TwoStepError as exc:
            messages.error(request, str(exc))
            return redirect("account_security")
        del request.session[APP_KEY_SESSION]
        messages.success(request, _("Your authenticator app is set up."))
        return _after_first_method(request, was_on)
    secret = b32encode(unhexlify(key)).decode("ascii")
    otpauth_url = get_otpauth_url(
        accountname=request.user.email or request.user.get_username(),
        secret=secret,
        issuer=settings.TWO_FACTOR_ISSUER,
    )
    return render(
        request,
        "accounts/security_app.html",
        {
            "form": form,
            "qr_svg": _qr_svg(otpauth_url),
            "secret": " ".join(secret[i : i + 4] for i in range(0, len(secret), 4)),
            "otpauth_url": otpauth_url,
        },
    )


@never_cache
@login_required
def security_passkey(request):
    """Add a passkey: the browser asks the device (phone, laptop, security
    key) to make one, and posts what it made (CoderDojo.initPasskey)."""
    _own_account(request)
    if response := _unverified(request):
        return response
    error = None
    if request.method == "POST":
        form = PasskeySetupForm(device=None, request=request, data=request.POST)
        if form.is_valid():
            was_on = two_step.is_on(request.user)
            try:
                two_step.add_passkey(request, form.cleaned_data)
            except two_step.TwoStepError as exc:
                error = str(exc)
            else:
                messages.success(request, _("Your passkey is added."))
                return _after_first_method(request, was_on)
        else:
            error = " ".join(form.errors.get("token", [])) or _("That passkey couldn't be checked. Please try again.")
    # A new, unbound form puts fresh options (and challenge) in the session.
    PasskeySetupForm(device=None, request=request)
    return render(
        request,
        "accounts/security_passkey.html",
        {
            "error": error,
            "passkey_options": request.session.get("webauthn_creation_options"),
        },
    )


@never_cache
@login_required
def security_backup_codes(request):
    """Backup codes: how many are left, and making a new set (shown once)."""
    _own_account(request)
    if response := _unverified(request):
        return response
    if not two_step.is_on(request.user):
        return redirect("account_security")
    if request.method == "POST":
        request.session[NEW_CODES_SESSION] = two_step.make_backup_codes(request.user)
        return redirect("account_security_backup_codes")
    return render(
        request,
        "accounts/security_backup_codes.html",
        {
            "codes": request.session.pop(NEW_CODES_SESSION, None),
            "codes_left": two_step.backup_codes_left(request.user),
        },
    )


DEVICE_MODELS = {two_step.APP: TOTPDevice, two_step.PASSKEY: WebauthnDevice}


@never_cache
@login_required
def security_remove(request, kind, device_id):
    """Remove one app or passkey, confirmed with the password."""
    _own_account(request)
    if response := _unverified(request):
        return response
    model = DEVICE_MODELS.get(kind)
    device = model and model.objects.filter(pk=device_id, user=request.user, confirmed=True).first()
    if device is None:
        raise Http404
    last = len(two_step.methods(request.user)) == 1
    blocked = two_step.requirement_blocks_removal(request.user, device)
    form = ConfirmIdentityForm(request.user, request.POST if request.method == "POST" else None, request=request)
    if request.method == "POST" and not blocked and form.is_valid():
        try:
            two_step.remove(request.user, device)
        except two_step.TwoStepError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Two-step login is off.") if last else _("That sign-in method is removed."))
        return redirect("account_security")
    return render(
        request,
        "accounts/security_confirm.html",
        {
            "form": form,
            "blocked": blocked,
            "kind": kind,
            "device": device,
            "last": last,
            "action": reverse("account_security_remove", kwargs={"kind": kind, "device_id": device.pk}),
        },
    )


@never_cache
@login_required
def security_turn_off(request):
    """Turn two-step login off: every app, passkey and backup code goes."""
    _own_account(request)
    if response := _unverified(request):
        return response
    if not two_step.is_on(request.user):
        return redirect("account_security")
    blocked = two_step.requirement_blocks_removal(request.user)
    form = ConfirmIdentityForm(request.user, request.POST if request.method == "POST" else None, request=request)
    if request.method == "POST" and not blocked and form.is_valid():
        try:
            two_step.turn_off(request.user)
        except two_step.TwoStepError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Two-step login is off."))
        return redirect("account_security")
    return render(
        request,
        "accounts/security_confirm.html",
        {
            "form": form,
            "blocked": blocked,
            "kind": None,
            "last": True,
            "action": reverse("account_security_turn_off"),
        },
    )


@login_required
@require_POST
def security_forget_browser(request):
    """Stop remembering this browser: the next login asks for the second step
    again. (Changing the password forgets every browser.)"""
    _own_account(request)
    response = redirect("account_security")
    for key in request.COOKIES:
        if key.startswith(REMEMBER_COOKIE_PREFIX):
            response.delete_cookie(key, domain=settings.TWO_FACTOR_REMEMBER_COOKIE_DOMAIN)
    messages.success(request, _("This browser is no longer remembered."))
    return response


# --- How the account logs in: a password or a login link (DATA_MODEL.md §24) ---


@never_cache
@login_required
def security_login_method(request):
    """Switch to logging in with a link: confirmed with the password, then
    from the mailbox (login_links.request_switch_to_link). An account on a
    link switches back by setting a password (security_set_password)."""
    _own_account(request)
    if response := _unverified(request):
        return response
    if request.user.uses_login_link:
        return redirect("account_security_password")
    form = ConfirmIdentityForm(request.user, request.POST if request.method == "POST" else None, request=request)
    if request.method == "POST" and form.is_valid():
        try:
            login_links.request_switch_to_link(request.user)
        except login_links.LoginLinkError as error:
            form.add_error(None, error.message)
        else:
            return render(
                request,
                "accounts/security_login_method.html",
                {"sent": True, "valid_hours": login_links.SWITCH_VALID_HOURS},
            )
    return render(request, "accounts/security_login_method.html", {"form": form})


@never_cache
@login_required
def security_set_password(request):
    """An account on a login link sets a password, and logs in with it from
    then on. Needs a recent login (accounts.reauth), since there's no old
    password to ask for."""
    _own_account(request)
    if response := _unverified(request):
        return response
    if not request.user.uses_login_link:
        return redirect("change_password")
    form = LinkToPasswordForm(request.user, request.POST if request.method == "POST" else None, request=request)
    if request.method == "POST" and form.is_valid():
        user = login_links.switch_to_password(request.user, form.cleaned_data["new_password1"])
        update_session_auth_hash(request, user)  # the other sessions end, this one stays
        messages.success(request, _("You now log in with your password."))
        return redirect("account_security")
    return render(request, "accounts/security_set_password.html", {"form": form})


@never_cache
def security_login_method_confirm(request, uidb64, token):
    """The link from the `login_method_confirm` mail. GET asks, POST
    switches (so a mail scanner that opens the link changes nothing). Works
    logged out too: the mailbox is the proof. Logged in as another account:
    404."""
    template = "accounts/security_login_method_confirm.html"
    user = login_links.user_from_switch_link(uidb64, token)
    if user is None:
        return render(request, template, {"invalid": True}, status=400)
    if request.user.is_authenticated and request.user.pk != user.pk:
        raise Http404
    if request.method != "POST":
        return render(request, template, {"account": user})
    try:
        user = login_links.switch_to_link(user)
    except login_links.LoginLinkError as error:
        return render(request, template, {"error": error.message}, status=400)
    if request.user.is_authenticated:
        update_session_auth_hash(request, user)  # the other sessions end, this one stays
        messages.success(request, _("From now on you log in with a link we mail you."))
        return redirect("account_security")
    return render(request, template, {"done": user})
