from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from geo.models import Municipality

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


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass


class LoginForm(forms.Form):
    email = forms.CharField(
        label=_("Email"),
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
