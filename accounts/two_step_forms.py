"""Forms for two-step login (accounts/two_step.py), on top of
django-two-factor-auth's and django-otp's: the same checks, with the site's
styling and wording (the packages' own translations don't match our tone)."""

from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy
from two_factor.forms import AuthenticationTokenForm, BackupTokenForm, TOTPDeviceForm
from two_factor.plugins.webauthn.forms import WebauthnAuthenticationTokenForm, WebauthnDeviceValidationForm

INPUT = "cd-form__input body"

OTP_ERROR_MESSAGES = {
    "token_required": _("Please enter the code."),
    "invalid_token": _("That code isn't right. Please check it and try again."),
    "n_failed_attempts": ngettext_lazy(
        "Too many wrong tries (%(failure_count)d). Please wait a moment and try again.",
        "Too many wrong tries (%(failure_count)d). Please wait a moment and try again.",
        "failure_count",
    ),
    "verification_not_allowed": _("Checking codes is paused for a moment. Please try again soon."),
    "device_required": _("Please choose how you want to confirm it's you."),
}


class _StyledTokenMixin:
    """django-two-factor-auth's login passes a token form the arguments its
    __init__ names (`user`, `initial_device`, `request`), so each form below
    keeps those names explicitly and then calls _style()."""

    otp_error_messages = {**AuthenticationTokenForm.otp_error_messages, **OTP_ERROR_MESSAGES}
    token_label = _("Code")

    def _style(self):
        self.fields["otp_token"].label = self.token_label
        self.fields["otp_token"].widget.attrs["class"] = INPUT
        if "remember" in self.fields:
            self.fields["remember"].label = _("Don't ask again in this browser for 30 days")


class CodeTokenForm(_StyledTokenMixin, AuthenticationTokenForm):
    """The login's second step with the six-digit code of an authenticator app."""

    def __init__(self, user, initial_device, **kwargs):
        super().__init__(user, initial_device, **kwargs)
        self._style()
        self.fields["otp_token"].widget.attrs.update({"inputmode": "numeric", "placeholder": "123456"})


class BackupCodeForm(_StyledTokenMixin, BackupTokenForm):
    """The login's second step with one of the account's backup codes."""

    token_label = _("Backup code")

    def __init__(self, user, initial_device, **kwargs):
        super().__init__(user, initial_device, **kwargs)
        self._style()


class PasskeyTokenForm(_StyledTokenMixin, WebauthnAuthenticationTokenForm):
    """The login's second step with a passkey: the browser fills the hidden
    field (CoderDojo.initPasskey in bundle.js)."""

    token_label = _("Passkey")
    otp_error_messages = {
        **_StyledTokenMixin.otp_error_messages,
        "invalid_token": _("That passkey couldn't be checked. Please try again."),
    }

    def __init__(self, user, initial_device, request, **kwargs):
        super().__init__(user, initial_device, request, **kwargs)
        self._style()
        self.fields["otp_token"].widget = forms.HiddenInput()
        self.fields["otp_token"].required = False  # an empty answer gets token_required, not a field error

    def _verify_token(self, user, token, device=None):
        try:
            return super()._verify_token(user, token, device)
        except (forms.ValidationError, KeyError) as exc:
            # KeyError: the challenge is gone from the session (another tab, or a replay).
            raise forms.ValidationError(self.otp_error_messages["invalid_token"], code="invalid_token") from exc


class AppSetupForm(TOTPDeviceForm):
    """Adding an authenticator app: the first code it shows proves it's set up."""

    error_messages = {"invalid_token": _("That code isn't right. Check the app shows CoderDojo Belgium, then try the newest code.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["token"]
        field.label = _("The code the app shows")
        field.widget.attrs.update({"class": INPUT, "placeholder": "123456"})


class PasskeySetupForm(WebauthnDeviceValidationForm):
    """Adding a passkey: the browser fills the hidden field with what the
    device made (CoderDojo.initPasskey in bundle.js)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["token"].widget = forms.HiddenInput()
        self.fields["token"].error_messages["required"] = _("Your browser didn't make a passkey. Please try again.")

    def clean_token(self):
        try:
            return super().clean_token()
        except forms.ValidationError as exc:
            raise forms.ValidationError(_("That passkey couldn't be checked. Please try again.")) from exc
        except KeyError as exc:  # the challenge is gone from the session
            raise forms.ValidationError(_("That took too long. Please try again.")) from exc


class ConfirmPasswordForm(forms.Form):
    """Asks for the account's password before a change that weakens the login."""

    password = forms.CharField(
        label=_("Your password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"class": INPUT, "autocomplete": "current-password"}),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError(_("That password isn't right."))
        return password
