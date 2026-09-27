import re

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UsernameField,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.functional import cached_property, lazy
from django.utils.safestring import SafeString
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from core.image_library import library_filename
from geo.models import Municipality

from .models import Ninja, SignInRequirement, User
from .template_avatars import TEMPLATE_KID_AVATARS


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
    """The parent/guardian half of the family-registration page; the
    children are ChildRowsFormSet, next to it."""

    # The input classes come from core.forms.SiteBoundField.
    name = forms.CharField(label=_("Full name"), max_length=150, widget=forms.TextInput(attrs={"placeholder": "Jane Doe"}))
    email = forms.EmailField(label=_("Email"), widget=forms.EmailInput(attrs={"placeholder": "jane.doe@example.com"}))
    phone = forms.CharField(
        label=_("Phone"), required=False, max_length=30,
        help_text=_("Only used if we need to reach you during a session."),
        widget=forms.TextInput(attrs={"placeholder": "+32 4xx xx xx xx"}),
    )
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput())
    postal_code = forms.CharField(
        label=_("Postcode"), required=False, max_length=4,
        help_text=_("So we can tell you about dojos and sessions near you."),
        widget=forms.TextInput(attrs={"placeholder": "9000", "inputmode": "numeric"}),
    )
    preferred_language = forms.ChoiceField(label=_("Language for emails"), required=False, choices=settings.LANGUAGES)
    consent = forms.BooleanField(
        label=_("I am the parent or legal guardian of the children listed below."), required=True,
    )
    # Optional: the children's details may choose which mails the family
    # gets (accounts.consent). Never needed to sign a child up.
    child_data_mail = forms.BooleanField(required=False, widget=forms.CheckboxInput())
    # The newsletter needs an explicit opt-in (mailing.categories): unticked.
    newsletter = forms.BooleanField(
        label=_("Send me the CoderDojo Belgium newsletter and news about events like Coolest Projects and CoderDojo Girlz."),
        required=False,
    )

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


class ConfirmPasswordForm(forms.Form):
    """Asks for the account's password before a change that can't be taken
    back or weakens the login (turning off two-step login, deleting the
    account)."""

    password = forms.CharField(
        label=_("Your password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, user, *args, label=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if label:
            self.fields["password"].label = label

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError(_("That password isn't right."))
        return password


class ChildLoginForm(forms.Form):
    """The child page's "Own login" card: the child's own email address
    (accounts.views.ninja_login_create). The rules about which address may be
    used live in accounts.child_accounts.give_login; the view adds its
    ChildAccountError to the field."""

    # Not required here: an empty address gets the service's own message.
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"autocomplete": "off", "required": True}))

    def __init__(self, child, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = lazy(lambda: _("%(name)s's email address") % {"name": child.name}, str)()
        if child.account is not None:
            self.fields["email"].initial = child.account.email


class LenientChoiceField(forms.ChoiceField):
    """A choice that's never an error: anything unknown (or missing) becomes
    `fallback`. For optional pickers where a stale or tampered value should
    just fall back, like the child's gender or avatar."""

    def __init__(self, *args, fallback="", **kwargs):
        self.fallback = fallback
        super().__init__(*args, required=False, **kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        return value if self.valid_value(value) else self.fallback


class ChildForm(forms.ModelForm):
    """A child's details, as the family enters them: Add a child
    (AddChildForm) and the child page's edit header (EditChildForm). The
    7–17 rule on the date of birth is Ninja.clean()'s (only for a date that
    changes)."""

    gender = LenientChoiceField(label=_("Gender (optional)"), choices=Ninja.GENDER_CHOICES, fallback=Ninja.UNSPECIFIED)
    # A standard avatar (accounts.views._set_icon links it); anything else
    # leaves the photo as it is.
    icon = LenientChoiceField(label=_("Avatar"), choices=TEMPLATE_KID_AVATARS)

    class Meta:
        model = Ninja
        fields = ["name", "family_name", "date_of_birth", "gender", "allergies_notes"]
        labels = {
            "name": _("First name"),
            "family_name": _("Family name"),
            "allergies_notes": _("Allergies or notes (optional)"),
        }
        help_texts = {
            "allergies_notes": _("Only the champion (the person running the dojo) sees this, on the list of a session your child is signed up for."),
        }
        error_messages = {
            "name": {"required": _("First name is required.")},
            "family_name": {"required": _("Family name is required.")},
        }
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "allergies_notes": forms.Textarea(attrs={"rows": 2, "placeholder": _("None")}),
        }


class AddChildForm(ChildForm):
    """The account page's "Register another child" form (accounts.views.add_ninja)."""

    # The approved wording is a partial (_child_data_consent.html), so the
    # page writes this checkbox's label itself.
    consent = forms.BooleanField(required=False)

    field_order = ["icon", "name", "family_name", "date_of_birth", "gender", "allergies_notes"]

    def __init__(self, *args, guardian, **kwargs):
        kwargs.setdefault("auto_id", "ac-%s")
        kwargs.setdefault("initial", {"family_name": guardian.last_name, "gender": Ninja.UNSPECIFIED})
        super().__init__(*args, **kwargs)
        self.fields["family_name"].required = True
        self.fields["date_of_birth"].label = _("Date of birth (optional)")


class EditChildForm(ChildForm):
    """The child page's edit header (accounts.views.edit_ninja). A field the
    post leaves out keeps what's stored, and the family name stays optional:
    a child added before it was asked for can still be edited."""

    KEPT_WHEN_MISSING = ["family_name", "date_of_birth", "gender", "allergies_notes", "home_dojo"]

    home_dojo = forms.ModelChoiceField(label=_("Home dojo"), queryset=None, required=False, empty_label=_("None yet"))

    field_order = ["name", "family_name", "date_of_birth", "gender", "home_dojo", "icon", "allergies_notes"]

    def __init__(self, *args, **kwargs):
        from django.db.models import Q

        from dojos.models import Dojo

        from . import home_dojo

        kwargs.setdefault("auto_id", "ec-%s")
        super().__init__(*args, **kwargs)
        child = self.instance
        self.fields["name"].widget.attrs["autofocus"] = True
        self.fields["date_of_birth"].label = _("Date of birth")
        # The public dojos, plus the current one if it's no longer public.
        self.fields["home_dojo"].queryset = Dojo.objects.filter(
            Q(pk__in=home_dojo.home_dojo_choices().values("pk")) | Q(pk=child.home_dojo_id)
        ).order_by("name")
        self.fields["home_dojo"].label_from_instance = lambda dojo: dojo.name
        self.fields["home_dojo"].initial = child.home_dojo_id
        self.fields["icon"].initial = library_filename(child.photo, "ninjas")
        if self.is_bound:
            data = self.data.copy()
            for name in self.KEPT_WHEN_MISSING:
                if name not in data:
                    data[name] = self.get_initial_for_field(self.fields[name], name) or ""
            self.data = data


class SignUpChildForm(ChildForm):
    """One child's row on family sign-up (ChildRowsFormSet)."""

    icon = None

    class Meta(ChildForm.Meta):
        labels = {**ChildForm.Meta.labels, "date_of_birth": _("Date of birth"), "allergies_notes": _("Allergies or notes")}
        help_texts = {**ChildForm.Meta.help_texts}
        error_messages = {**ChildForm.Meta.error_messages, "date_of_birth": {"required": _("Date of birth is required.")}}
        widgets = {
            **ChildForm.Meta.widgets,
            "name": forms.TextInput(attrs={"placeholder": _("Sam")}),
            "family_name": forms.TextInput(attrs={"placeholder": _("Peeters")}),
            "allergies_notes": forms.TextInput(attrs={"placeholder": _("None")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["family_name"].required = True
        self.fields["date_of_birth"].required = True
        self.fields["gender"].label = _("Gender")
        self.fields["gender"].help_text = _("Optional, never shown publicly. Lets us tell you about girls' sessions.")
        self.fields["gender"].initial = Ninja.UNSPECIFIED


class ChildRowsFormSet(forms.formset_factory(SignUpChildForm, extra=0)):
    """The children on family sign-up: rows numbered child-<n>-..., added
    and removed on the page (_child_rows_script.html clones `empty_form`).
    Removing a row leaves a gap in the numbering, so the rows are the
    numbers the post actually has, each one filled in, and at least one."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("prefix", "child")
        super().__init__(*args, **kwargs)

    @cached_property
    def forms(self):
        if not self.is_bound:
            return [self._construct_form(0)]
        row = re.compile(rf"^{re.escape(self.prefix)}-(\d+)-name$")
        numbers = sorted({int(match[1]) for key in self.data if (match := row.match(key))})
        return [self._construct_form(n, empty_permitted=False) for n in numbers]

    def clean(self):
        if not self.forms:
            raise ValidationError(_("Add at least one child."))
