from django import forms
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm


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
