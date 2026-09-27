from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UsernameField,
)
from django.contrib.auth import password_validation
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.functional import lazy
from django.utils.safestring import SafeString
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from geo.models import Municipality

from .models import SignInRequirement, User


def _password_rules():
    """The password rules as a list (Django's own texts), in the visitor's
    language: Django builds this help text once, when the form class loads."""
    return password_validation.password_validators_help_text_html()


class NewPasswordLabelsMixin:
    """The site's wording for a new password and its confirmation, and the
    rules as the new password's help text."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = _("New password")
        self.fields["new_password1"].help_text = lazy(_password_rules, SafeString)()
        self.fields["new_password2"].label = _("Confirm new password")
        self.fields["new_password2"].help_text = ""


class ForcedPasswordChangeForm(NewPasswordLabelsMixin, PasswordChangeForm):
    """PasswordChangeForm with the site's wording. Still requires the current
    (temporary) password — a user who's been emailed one shouldn't be able to
    skip straight past it."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["old_password"].label = (
            _("Temporary password") if user.must_change_password else _("Current password")
        )


class StyledPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = _("Email")

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email,
                  html_email_template_name=None):
        """Every mail goes through the mail engine (mailing.services.send):
        queued as account (`service`) mail, in the account's language, with
        the reset link built from the request's own domain."""
        from mailing.categories import MailCategory
        from mailing.services import send_or_log

        path = reverse("password_reset_confirm", kwargs={"uidb64": context["uid"], "token": context["token"]})
        send_or_log(context["user"], MailCategory.SERVICE, "password_reset",
             {"reset_url": f"{context['protocol']}://{context['domain']}{path}"})


class StyledSetPasswordForm(NewPasswordLabelsMixin, SetPasswordForm):
    pass


class LoginForm(AuthenticationForm):
    """The login's first step (accounts.views.LoginView): email or username
    (accounts.backends.EmailOrUsernameBackend) and password. A Django
    AuthenticationForm, as django-two-factor-auth's login expects, so its
    field is called `username`."""

    username = UsernameField(
        label=_("Email"),
        widget=forms.TextInput(attrs={
            "class": "cd-form__input body",
            "placeholder": "you@example.com",
            "autofocus": True,
            "autocomplete": "username",
        }),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "cd-form__input body", "autocomplete": "current-password"}),
    )
    error_messages = {
        "invalid_login": _("That email/password combination doesn't match an account."),
        "inactive": _("That email/password combination doesn't match an account."),
    }


class RegisterGuardianForm(forms.Form):
    """The parent/guardian half of the family-registration page — the
    children are handled separately (see accounts.views._parse_child_rows)
    since they're a dynamic, JS-managed set of rows rather than a fixed
    set of fields a Form/formset maps cleanly onto."""

    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Jane Doe"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "cd-form__input body", "placeholder": "jane.doe@example.com"}),
    )
    phone = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "+32 4xx xx xx xx"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "cd-form__input body"}),
    )
    postal_code = forms.CharField(
        required=False,
        max_length=4,
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "9000", "inputmode": "numeric"}),
    )
    preferred_language = forms.ChoiceField(
        required=False,
        choices=settings.LANGUAGES,
        widget=forms.Select(attrs={"class": "cd-form__input body"}),
    )
    consent = forms.BooleanField(required=True, widget=forms.CheckboxInput())
    # Optional: the children's details may choose which mails the family
    # gets (accounts.consent). Never needed to sign a child up.
    child_data_mail = forms.BooleanField(required=False, widget=forms.CheckboxInput())
    # The newsletter needs an explicit opt-in (mailing.categories): unticked.
    newsletter = forms.BooleanField(required=False, widget=forms.CheckboxInput())

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("An account already exists with this email."))
        return email

    def clean_postal_code(self):
        postal_code = self.cleaned_data["postal_code"].strip()
        if postal_code and not Municipality.objects.filter(postal_code=postal_code).exists():
            raise ValidationError(_("That isn't a Belgian postcode we know."))
        return postal_code

    def clean_password(self):
        password = self.cleaned_data["password"]
        # Raises ValidationError with one message per failed validator —
        # Django's own AUTH_PASSWORD_VALIDATORS (website/settings.py), same
        # ones enforced everywhere else a password is set.
        validate_password(password)
        return password


class SignInPolicyForm(forms.Form):
    """The organisation's sign-in policy (/manage/security/, accounts/manage.py):
    per role a level and the day it's required from. Field names are
    `level_<role>` and `from_<role>`."""

    def __init__(self, *args, requirements=None, **kwargs):
        super().__init__(*args, **kwargs)
        requirements = requirements or {}
        for role, label in SignInRequirement.ROLE_CHOICES:
            current = requirements.get(role)
            self.fields[f"level_{role}"] = forms.ChoiceField(
                label=label, choices=SignInRequirement.LEVEL_CHOICES,
                initial=current.level if current else SignInRequirement.PASSWORD,
                widget=forms.Select(attrs={"class": "cd-form__input body"}),
            )
            self.fields[f"from_{role}"] = forms.DateField(
                label=_("Required from"), required=False,
                initial=current.required_from if current else None,
                widget=forms.DateInput(
                    attrs={"class": "cd-form__input body", "type": "date",
                           "aria-label": format_lazy("{}: {}", label, _("Required from"))},
                    format="%Y-%m-%d",
                ),
            )

    def rows(self):
        return [
            (role, label, self[f"level_{role}"], self[f"from_{role}"])
            for role, label in SignInRequirement.ROLE_CHOICES
        ]

    def save(self, updated_by):
        """Store every role's row; returns the roles that changed."""
        changed = []
        for role, _label in SignInRequirement.ROLE_CHOICES:
            level = self.cleaned_data[f"level_{role}"]
            required_from = self.cleaned_data[f"from_{role}"] if level != SignInRequirement.PASSWORD else None
            row = SignInRequirement.objects.filter(role=role).first()
            if row is None:
                if level == SignInRequirement.PASSWORD:
                    continue
                row = SignInRequirement(role=role)
            elif row.level == level and row.required_from == required_from:
                continue
            row.level, row.required_from, row.updated_by = level, required_from, updated_by
            row.save()
            changed.append(role)
        return changed
