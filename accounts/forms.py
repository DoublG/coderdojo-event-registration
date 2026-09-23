from django import forms
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import User


class StyledFormMixin:
    """Applies the site's input styling to every field — used for the
    handful of forms built on Django's stock auth forms, which otherwise
    render plain unstyled widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "cd-form__input body"


class ForcedPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    """PasswordChangeForm, styled to match the rest of the auth pages.
    Still requires the current (temporary) password — a user who's been
    emailed one shouldn't be able to skip straight past it."""


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass


class LoginForm(forms.Form):
    email = forms.CharField(
        label="Email",
        widget=forms.TextInput(attrs={
            "class": "cd-form__input body",
            "placeholder": "you@example.com",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "cd-form__input body"}),
    )


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
    consent = forms.BooleanField(required=True, widget=forms.CheckboxInput())

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account already exists with this email.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        # Raises ValidationError with one message per failed validator —
        # Django's own AUTH_PASSWORD_VALIDATORS (website/settings.py), same
        # ones enforced everywhere else a password is set.
        validate_password(password)
        return password
