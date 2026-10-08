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


# lazy() once at module level, never per form: each call defines a new class
# (MEMORY_PROFILE.md). Calling the result per form is cheap.
password_rules_lazy = lazy(_password_rules, SafeString)


def _child_email_label(name):
    return _("%(name)s's email address") % {"name": name}


child_email_label_lazy = lazy(_child_email_label, str)


class NewPasswordLabelsMixin:
    """The site's wording for a new password and its confirmation, and the
    rules as the new password's help text."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = _("New password")
        self.fields["new_password1"].help_text = password_rules_lazy()
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

    def get_users(self, email):
        """Django's accounts with a usable password, plus the accounts that
        log in with a link (they have none): those get a login link
        instead of a reset (send_mail)."""
        active = User._default_manager.filter(email__iexact=email, is_active=True)
        return (
            user
            for user in active
            if (user.has_usable_password() or user.uses_login_link) and user.email.casefold() == email.casefold()
        )

    def send_mail(
        self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None
    ):
        """Every mail goes through the mail engine (mailing.services.send):
        queued as account (`service`) mail, in the account's language, with
        the reset link built from the request's own domain. An account that
        logs in with a link has no password to reset: it gets a login link
        (accounts/login_links.py, DATA_MODEL.md §24)."""
        from mailing.categories import MailCategory
        from mailing.services import send_or_log

        from .login_links import send_login_link

        if context["user"].uses_login_link:
            send_login_link(context["user"])
            return
        path = reverse("password_reset_confirm", kwargs={"uidb64": context["uid"], "token": context["token"]})
        send_or_log(
            context["user"],
            MailCategory.SERVICE,
            "password_reset",
            {"reset_url": f"{context['protocol']}://{context['domain']}{path}"},
        )


class StyledSetPasswordForm(NewPasswordLabelsMixin, SetPasswordForm):
    pass


class LinkToPasswordForm(StyledSetPasswordForm):
    """Switching from a login link back to a password
    (accounts.security_views.security_set_password): a new password, from a
    session that logged in in the last few minutes (accounts.reauth)."""

    def __init__(self, user, *args, request=None, **kwargs):
        from .reauth import recently_authenticated

        super().__init__(user, *args, **kwargs)
        self.uses_link = True
        self.recent = request is not None and recently_authenticated(request)

    def clean(self):
        cleaned_data = super().clean()
        if not self.recent:
            raise forms.ValidationError(
                _("Confirm it's you first: we mail you a login link that brings you back here."),
                code="not_recent",
            )
        return cleaned_data


class LoginForm(AuthenticationForm):
    """The login's first step (accounts.views.LoginView): email or username
    (accounts.backends.EmailOrUsernameBackend) and password. A Django
    AuthenticationForm, as django-two-factor-auth's login expects, so its
    field is called `username`."""

    username = UsernameField(
        label=_("Email"),
        widget=forms.TextInput(
            attrs={
                "class": "cd-form__input body",
                "placeholder": "you@example.com",
                "autofocus": True,
                "autocomplete": "username",
            }
        ),
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


class LoginLinkForm(forms.Form):
    """The first step of a login from an emailed link (accounts.views.
    LoginLinkView): no fields, the link is the proof. Like LoginForm, it
    leaves the account in `user_cache` for django-two-factor-auth's login,
    which then asks for the second step when the account has one."""

    def __init__(self, *args, link_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_cache = link_user

    def clean(self):
        if self.user_cache is None:
            raise ValidationError(_("This login link has expired or was already used. Ask for a new one."))
        return super().clean()

    def get_user(self):
        return self.user_cache


class LoginLinkRequestForm(forms.Form):
    """Asking for a login link (accounts.views.login_link_request)."""

    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autofocus": True, "autocomplete": "email"}),
    )


def clean_belgian_postal_code(value):
    """An optional Belgian postcode (User.postal_code): empty, or one of
    geo.Municipality's. Shared by family sign-up and the account's details."""
    postal_code = value.strip()
    if postal_code and not Municipality.objects.filter(postal_code=postal_code).exists():
        raise ValidationError(_("That isn't a Belgian postcode we know."))
    return postal_code


class LoginMethodChoiceMixin:
    """Sign-up's "How do you want to log in?" (DATA_MODEL.md §24): a
    password, or a login link mailed each time; the password is only asked
    for the first. The page hides the password field while the link is
    chosen (plain CSS on the radio)."""

    def _add_login_method(self):
        self.fields["login_method"] = forms.ChoiceField(
            label=_("How do you want to log in?"),
            choices=[
                (User.LOGIN_PASSWORD, _("With a password")),
                (User.LOGIN_LINK, _("With a link we mail you each time (no password to remember)")),
            ],
            initial=User.LOGIN_PASSWORD,
            # Not sent at all (an older page): a password, as before.
            required=False,
            widget=forms.RadioSelect,
        )
        self.fields["password"].required = False

    def clean_login_method(self):
        return self.cleaned_data["login_method"] or User.LOGIN_PASSWORD

    def clean_password(self):
        password = self.cleaned_data["password"]
        if password and self.data.get(self.add_prefix("login_method")) != User.LOGIN_LINK:
            # Raises ValidationError with one message per failed validator —
            # Django's own AUTH_PASSWORD_VALIDATORS (website/settings.py), same
            # ones enforced everywhere else a password is set.
            validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("login_method") == User.LOGIN_PASSWORD and not cleaned_data.get("password"):
            if "password" not in self.errors:
                self.add_error("password", forms.ValidationError(_("Choose a password."), code="required"))
        return cleaned_data

    @property
    def uses_link(self):
        return self.cleaned_data.get("login_method") == User.LOGIN_LINK


class _UniqueEmailMixin:
    """An email field with the site's "already in use" check, shared by every
    public sign-up form (RegisterGuardianForm, RegisterIndividualForm)."""

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("An account already exists with this email."))
        return email


class RegisterGuardianForm(_UniqueEmailMixin, LoginMethodChoiceMixin, forms.Form):
    """The parent/guardian half of the family-registration page; the
    children are ChildRowsFormSet, next to it."""

    # The input classes come from core.forms.SiteBoundField.
    name = forms.CharField(
        label=_("Full name"), max_length=150, widget=forms.TextInput(attrs={"placeholder": "Jane Doe"})
    )
    email = forms.EmailField(label=_("Email"), widget=forms.EmailInput(attrs={"placeholder": "jane.doe@example.com"}))
    phone = forms.CharField(
        label=_("Phone"),
        required=False,
        max_length=30,
        help_text=_("Only used if we need to reach you during a session."),
        widget=forms.TextInput(attrs={"placeholder": "+32 4xx xx xx xx"}),
    )
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput())
    postal_code = forms.CharField(
        label=_("Postcode"),
        required=False,
        max_length=4,
        help_text=_("So we can tell you about dojos and sessions near you."),
        widget=forms.TextInput(attrs={"placeholder": "9000", "inputmode": "numeric"}),
    )
    preferred_language = forms.ChoiceField(label=_("Language for emails"), required=False, choices=settings.LANGUAGES)
    consent = forms.BooleanField(
        label=_("I am the parent or legal guardian of the children listed below."),
        required=True,
    )
    # Optional: the children's details may choose which mails the family
    # gets (accounts.consent). Never needed to sign a child up.
    child_data_mail = forms.BooleanField(required=False, widget=forms.CheckboxInput())
    # The newsletter needs an explicit opt-in (mailing.categories): unticked.
    newsletter = forms.BooleanField(
        label=_(
            "Send me the CoderDojo Belgium newsletter and news about events like Coolest Projects and CoderDojo Girlz."
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_login_method()

    def clean_postal_code(self):
        return clean_belgian_postal_code(self.cleaned_data["postal_code"])


class RegisterIndividualForm(_UniqueEmailMixin, LoginMethodChoiceMixin, forms.Form):
    """Self-service sign-up for an adult with no children of their own who
    still wants to get involved (accounts.views.register_individual): start a
    dojo or volunteer, both of which need a logged-in account first
    (applications.views.register_dojo/register_helper). Same fields as
    RegisterGuardianForm, minus the children and their consent — there's
    nothing here about a child, and a parent who does have one already uses
    family sign-up instead."""

    name = forms.CharField(
        label=_("Full name"), max_length=150, widget=forms.TextInput(attrs={"placeholder": "Jane Doe"})
    )
    email = forms.EmailField(label=_("Email"), widget=forms.EmailInput(attrs={"placeholder": "jane.doe@example.com"}))
    phone = forms.CharField(
        label=_("Phone"),
        required=False,
        max_length=30,
        help_text=_("Only used if we need to reach you about your application."),
        widget=forms.TextInput(attrs={"placeholder": "+32 4xx xx xx xx"}),
    )
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput())
    postal_code = forms.CharField(
        label=_("Postcode"),
        required=False,
        max_length=4,
        help_text=_("So we can tell you about dojos near you."),
        widget=forms.TextInput(attrs={"placeholder": "9000", "inputmode": "numeric"}),
    )
    preferred_language = forms.ChoiceField(label=_("Language for emails"), required=False, choices=settings.LANGUAGES)
    newsletter = forms.BooleanField(
        label=_(
            "Send me the CoderDojo Belgium newsletter and news about events like Coolest Projects and CoderDojo Girlz."
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_login_method()

    def clean_postal_code(self):
        return clean_belgian_postal_code(self.cleaned_data["postal_code"])


class EditAccountForm(forms.ModelForm):
    """The account page's details (accounts.views.edit_account): name, phone
    and postcode. The email address is shown, not edited here: it's the
    login and where every mail goes, so changing it needs its own
    confirmed flow. The mail language stays on Mail preferences."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "postal_code"]
        labels = {
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "phone": _("Phone"),
            "postal_code": _("Postcode"),
        }
        # The model's help texts are English notes for the admin.
        help_texts = {
            "first_name": "",
            "last_name": "",
            "phone": _("Only used if we need to reach you during a session."),
            "postal_code": _("So we can tell you about dojos and sessions near you."),
        }
        # The input classes come from core.forms.SiteBoundField.
        widgets = {
            "phone": forms.TextInput(attrs={"placeholder": "+32 4xx xx xx xx", "autocomplete": "tel"}),
            "postal_code": forms.TextInput(
                attrs={"placeholder": "9000", "inputmode": "numeric", "autocomplete": "postal-code"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"

    def clean_postal_code(self):
        return clean_belgian_postal_code(self.cleaned_data["postal_code"])


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
                label=label,
                choices=SignInRequirement.LEVEL_CHOICES,
                initial=current.level if current else SignInRequirement.PASSWORD,
                widget=forms.Select(attrs={"class": "cd-form__input body"}),
            )
            self.fields[f"from_{role}"] = forms.DateField(
                label=_("Required from"),
                required=False,
                initial=current.required_from if current else None,
                widget=forms.DateInput(
                    attrs={
                        "class": "cd-form__input body",
                        "type": "date",
                        "aria-label": format_lazy("{}: {}", label, _("Required from")),
                    },
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


class ConfirmIdentityForm(forms.Form):
    """Asks the account to confirm it's them before a change that can't be
    taken back or weakens the login (turning off two-step login, deleting
    the account, a new email address, admin access): its password, or, for
    an account that logs in with a link and so has none, a login in the last
    few minutes (accounts.reauth, DATA_MODEL.md §24). Templates show it with
    accounts/partials/_confirm_identity.html."""

    password = forms.CharField(
        label=_("Your password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, user, *args, request=None, label=None, **kwargs):
        from .reauth import recently_authenticated

        super().__init__(*args, **kwargs)
        self.user = user
        self.uses_link = user.uses_login_link
        self.recent = self.uses_link and request is not None and recently_authenticated(request)
        if self.uses_link:
            del self.fields["password"]
        elif label:
            self.fields["password"].label = label

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError(_("That password isn't right."))
        return password

    def clean(self):
        cleaned_data = super().clean()
        if self.uses_link and not self.recent:
            raise forms.ValidationError(
                _("Confirm it's you first: we mail you a login link that brings you back here."),
                code="not_recent",
            )
        return cleaned_data


class AdminAccessForm(ConfirmIdentityForm):
    """Asking for the Django admin (accounts.admin_access, DATA_MODEL.md
    §23): why, and the password again."""

    reason = forms.CharField(
        label=_("Why do you need it?"),
        max_length=300,
        help_text=_("For example: fix a registration by hand. The other organisation admins see this."),
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    field_order = ["reason", "password"]


class OrganisationRolesForm(forms.Form):
    """An account's organisation roles on the People pages (DATA_MODEL.md
    §23). The page renders the checkboxes itself, each with what the role
    opens; accounts.organisation_people decides what's allowed."""

    roles = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        from .organisation_people import ROLES

        super().__init__(*args, **kwargs)
        self.fields["roles"].choices = [(role, label) for role, label, _description in ROLES]


class InvitationForm(OrganisationRolesForm):
    """Inviting someone without an account to organisation roles (the People
    pages, accounts.invitations, DATA_MODEL.md §23)."""

    name = forms.CharField(label=_("Their name"), max_length=150)
    email = forms.EmailField(label=_("Their email address"))
    language = forms.ChoiceField(label=_("Language of the invitation"), choices=settings.LANGUAGES)
    field_order = ["name", "email", "language", "roles"]


class InvitedSignUpForm(LoginMethodChoiceMixin, forms.Form):
    """Creating your own account from an organisation invitation: like family
    sign-up without the children, and the address is the invited one."""

    name = forms.CharField(label=_("Full name"), max_length=150)
    phone = forms.CharField(label=_("Phone"), required=False, max_length=30)
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput())
    preferred_language = forms.ChoiceField(label=_("Language for emails"), required=False, choices=settings.LANGUAGES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_login_method()
        self.order_fields(["name", "phone", "login_method", "password", "preferred_language"])


class _NewEmailMixin:
    """The new address of an email change, checked by the service that
    makes it (accounts.email_change.check_new_address)."""

    def clean_new_email(self):
        from .email_change import EmailChangeError, check_new_address

        new_email = self.cleaned_data["new_email"].strip()
        try:
            check_new_address(self.account, new_email)
        except EmailChangeError as error:
            raise forms.ValidationError(error.message) from None
        return new_email


def _new_email_field():
    return forms.EmailField(
        label=_("New email address"),
        help_text=_("We send a link there. The address only changes once you open it."),
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )


class ChangeEmailForm(_NewEmailMixin, ConfirmIdentityForm):
    """The family's own email change (accounts.views.change_email): the new
    address, and the password to show it's them."""

    new_email = _new_email_field()
    field_order = ["new_email", "password"]

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, label=_("Your password"), **kwargs)
        self.account = user


class OrganisationEmailChangeForm(_NewEmailMixin, forms.Form):
    """An organisation admin starts an email change for a family that lost
    its old mailbox (privacy.views.manage_privacy_email)."""

    new_email = _new_email_field()
    identity_checked = forms.BooleanField(
        label=_("I've checked that this request comes from the account holder."),
        required=True,
    )

    def __init__(self, account, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        self.fields["new_email"].help_text = _(
            "We send a link there. The address only changes once they open it; they don't need to log in for that."
        )


class ChildLoginForm(forms.Form):
    """The child page's "Own login" card: the child's own email address
    (accounts.views.ninja_login_create). The rules about which address may be
    used live in accounts.child_accounts.give_login; the view adds its
    ChildAccountError to the field."""

    # Not required here: an empty address gets the service's own message.
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"autocomplete": "off", "required": True}))

    login_method = forms.ChoiceField(
        label=_("How will they log in?"),
        choices=[
            (User.LOGIN_PASSWORD, _("With a password they choose")),
            (User.LOGIN_LINK, _("With a link we mail them each time (no password)")),
        ],
        initial=User.LOGIN_PASSWORD,
        required=False,
        widget=forms.RadioSelect,
    )

    def __init__(self, child, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = child_email_label_lazy(child.name)
        if child.account is not None:
            self.fields["email"].initial = child.account.email
            self.fields["login_method"].initial = child.account.login_method

    def clean_login_method(self):
        return self.cleaned_data["login_method"] or User.LOGIN_PASSWORD


class ChildEmailChangeForm(_NewEmailMixin, ConfirmIdentityForm):
    """A guardian changes the address of their child's login
    (accounts.views.ninja_login_email): the new address, and the guardian's
    own password (or recent login) to show it's them (DATA_MODEL.md §24)."""

    new_email = _new_email_field()
    field_order = ["new_email", "password"]

    def __init__(self, guardian, account, *args, **kwargs):
        super().__init__(guardian, *args, label=_("Your password"), **kwargs)
        self.account = account
        self.fields["new_email"].help_text = _(
            "We send a link there. The address only changes once it's opened; your child doesn't need to log in "
            "for that."
        )


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
            "allergies_notes": _(
                "Only the champion (the person running the dojo) sees this, on the list of a session your child is signed up for."
            ),
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
        # A photo that isn't one of the standard avatars (an upload, or none
        # yet) is kept unless another avatar is picked.
        current = library_filename(child.photo, "ninjas")
        if not current:
            keep = _("Keep the current photo") if child.photo else _("No avatar")
            self.fields["icon"].choices = [("", keep), *TEMPLATE_KID_AVATARS]
        self.fields["icon"].initial = current or ""
        if self.is_bound:
            data = self.data.copy()
            for name in self.KEPT_WHEN_MISSING:
                if name not in data:
                    data[name] = self.get_initial_for_field(self.fields[name], name) or ""
            self.data = data


class ChildAvatarForm(forms.Form):
    """A child's own login picks its avatar (accounts.views.ninja_avatar):
    one of the standard ones only. Nobody uploads a child's photo on the
    site (only the Django admin can set one), so there's no file field."""

    icon = forms.ChoiceField(label=_("Pick your avatar"), choices=TEMPLATE_KID_AVATARS, widget=forms.RadioSelect)

    def __init__(self, child, *args, **kwargs):
        kwargs.setdefault("auto_id", "av-%s")
        super().__init__(*args, **kwargs)
        self.fields["icon"].initial = library_filename(child.photo, "ninjas") or None


class SignUpChildForm(ChildForm):
    """One child's row on family sign-up (ChildRowsFormSet)."""

    icon = None

    class Meta(ChildForm.Meta):
        labels = {
            **ChildForm.Meta.labels,
            "date_of_birth": _("Date of birth"),
            "allergies_notes": _("Allergies or notes"),
        }
        help_texts = {**ChildForm.Meta.help_texts}
        error_messages = {
            **ChildForm.Meta.error_messages,
            "date_of_birth": {"required": _("Date of birth is required.")},
        }
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
