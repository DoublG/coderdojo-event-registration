import re

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import lazy
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

from .categories import CAN_OPT_OUT, DESCRIPTIONS, MailCategory, categories_for
from .models import Campaign, EmailTemplate, Journey, Segment
from .preferences import preferences_for


class MailPreferencesForm(forms.Form):
    """One checkbox per category the account can switch off, plus the mail
    language. Categories that can't be switched off are listed by the
    template, not as fields. (The postcode is on the account page's
    details, accounts.forms.EditAccountForm.)"""

    preferred_language = forms.ChoiceField(
        label=_("Language for emails"),
        choices=settings.LANGUAGES,
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        current = preferences_for(user)
        kwargs.setdefault("initial", {}).update(
            {
                "preferred_language": user.preferred_language or settings.LANGUAGES[0][0],
                **{f"category_{category}": subscribed for category, subscribed in current.items()},
            }
        )
        super().__init__(*args, **kwargs)
        self.categories = categories_for(user)
        for category in self.categories:
            if CAN_OPT_OUT[category]:
                self.fields[f"category_{category}"] = forms.BooleanField(
                    required=False,
                    label=category.label,
                    help_text=DESCRIPTIONS[category],
                )
        # Per child: may their details choose which mails we send (accounts.consent)?
        self.guardianships = (
            []
            if user.is_ninja
            else list(user.guardianships.select_related("ninja").order_by("ninja__name", "ninja__family_name"))
        )
        for guardianship in self.guardianships:
            self.fields[f"child_{guardianship.ninja_id}"] = forms.BooleanField(
                required=False,
                label=guardianship.ninja.full_name,
                initial=guardianship.consent_given_at is not None,
            )

    def category_fields(self):
        return [self[name] for name in self.fields if name.startswith("category_")]

    def child_fields(self):
        return [self[name] for name in self.fields if name.startswith("child_")]

    def child_consents(self):
        """(guardianship, given) for every child, from the cleaned data."""
        return [(g, self.cleaned_data[f"child_{g.ninja_id}"]) for g in self.guardianships]

    def always_on(self):
        return [(category.label, DESCRIPTIONS[category]) for category in self.categories if not CAN_OPT_OUT[category]]

    def chosen(self):
        """{category: subscribed} from the submitted checkboxes."""
        return {
            name.removeprefix("category_"): value
            for name, value in self.cleaned_data.items()
            if name.startswith("category_")
        }


# --- the organisation dashboard (mailing.manage) --------------------------------

VARIABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class MailingFormMixin:
    """What a campaign and a journey share: a kind of mail people can switch
    off, a template picked from the existing ones, an active segment, and
    template variables edited as "name: value" lines (stored in `context`)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = _("Name")
        self.fields["name"].help_text = ""
        self.fields["category"].label = _("Kind of mail")
        self.fields["category"].help_text = _("Only people who want this kind of mail get it.")
        self.fields["category"].choices = [(c.value, c.label) for c in MailCategory if CAN_OPT_OUT[c]]
        keys = EmailTemplate.objects.order_by("key").values_list("key", flat=True).distinct()
        self.fields["template_key"] = forms.ChoiceField(label=_("Template"), choices=[(k, k) for k in keys])
        self.fields["segment"].label = _("Segment")
        self.fields["segment"].queryset = Segment.objects.filter(is_active=True).order_by("name")
        self.fields["segment"].required = True
        if not self.is_bound:
            self.initial["variables"] = "\n".join(f"{k}: {v}" for k, v in (self.instance.context or {}).items())

    def clean_variables(self):
        variables = {}
        for number, line in enumerate(self.cleaned_data["variables"].splitlines(), 1):
            if not line.strip():
                continue
            name, sep, value = line.partition(":")
            name = name.strip()
            if not sep or not VARIABLE_RE.match(name):
                raise ValidationError(
                    _("Line %(number)s: write it as name: value (a name in lowercase letters and _).")
                    % {"number": number}
                )
            variables[name] = value.strip()
        return variables

    def save(self, commit=True):
        self.instance.context = self.cleaned_data["variables"]
        return super().save(commit)


def _variables_field():
    return forms.CharField(
        label=_("Template variables"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": _("signup_url: https://coolestprojects.org")}),
        help_text=_("One per line, as name: value. The template uses them as {{ name }}."),
    )


def _segments_help():
    """The Segment field's help, with a link to the Segments page."""
    return mark_safe(
        _('<a href="%(url)s">Segments</a> describe who gets it.') % {"url": reverse("manage_segment_list")}
    )


class CampaignForm(MailingFormMixin, forms.ModelForm):
    """A draft campaign: what (template + variables), to whom (segment),
    which kind of mail (only ones people can switch off) and when."""

    variables = _variables_field()

    class Meta:
        model = Campaign
        fields = ["name", "category", "template_key", "segment", "scheduled_at"]
        # The input classes come from core.forms.SiteBoundField.
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": _("Coolest Projects 2027")}),
            "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["scheduled_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["scheduled_at"].label = _("Send at")
        self.fields["scheduled_at"].help_text = _("Leave empty to send as soon as it's launched.")
        self.fields["segment"].help_text = lazy(_segments_help, SafeString)()

    def clean_scheduled_at(self):
        when = self.cleaned_data["scheduled_at"]
        if when and when <= timezone.now():
            raise ValidationError(_("Pick a time in the future, or leave it empty to send when launched."))
        return when


class SegmentForm(forms.ModelForm):
    class Meta:
        model = Segment
        fields = ["name", "description", "is_active"]
        # The input classes come from core.forms.SiteBoundField.
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": _("Families near Ghent")}),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": _("Who this is, in a sentence.")}),
        }
        labels = {
            "name": _("Name"),
            "description": _("Description"),
            "is_active": _("Active (offered when creating a campaign)"),
        }
        # The model's help texts are English notes for the admin.
        help_texts = {"name": "", "description": "", "is_active": ""}


class TemplateVersionForm(forms.ModelForm):
    """One language of an email template. The subject and body must be valid
    Django template syntax and render with example data, so a broken
    template never reaches anyone."""

    class Meta:
        model = EmailTemplate
        fields = ["subject", "body", "description"]
        labels = {"subject": _("Subject"), "body": _("Text"), "description": _("Description")}
        help_texts = {"description": _("When it's sent and which variables it uses.")}
        # The body keeps its own class: an 18-row text box styled like an input.
        widgets = {
            "body": forms.Textarea(attrs={"class": "cd-form__input body", "rows": 18, "spellcheck": "true"}),
            "description": forms.TextInput(),
        }

    def __init__(self, *args, sample_context=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sample_context = sample_context or {}

    def clean(self):
        from django.template import Context, Template, TemplateSyntaxError

        cleaned = super().clean()
        for field in ("subject", "body"):
            try:
                Template(cleaned.get(field, "")).render(Context(self.sample_context, autoescape=False))
            except TemplateSyntaxError as error:
                self.add_error(field, f"This doesn't work as a template: {error}")
            except Exception as error:  # a filter failing on the example data
                self.add_error(field, f"This fails with the example data: {error}")
        return cleaned


class NewTemplateForm(forms.Form):
    key = forms.SlugField(
        label=_("Name"),
        max_length=100,
        help_text=_("Lowercase, with _ between words, e.g. campaign_summer_camp."),
        widget=forms.TextInput(attrs={"placeholder": _("campaign_summer_camp")}),
    )
    category = forms.ChoiceField(label=_("Kind of mail"))
    description = forms.CharField(
        label=_("Description"),
        required=False,
        max_length=255,
        help_text=_("When it's used and which variables it takes."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [(c.value, c.label) for c in MailCategory if CAN_OPT_OUT[c]]

    def clean_key(self):
        key = self.cleaned_data["key"].replace("-", "_")
        if EmailTemplate.objects.filter(key=key).exists():
            raise ValidationError(_("A template with this name already exists."))
        return key


class JourneyForm(MailingFormMixin, forms.ModelForm):
    """A journey: the same what/whom/kind as a campaign, plus a cool-down."""

    variables = _variables_field()

    class Meta:
        model = Journey
        fields = ["name", "category", "template_key", "segment", "cooldown_days"]
        labels = {"cooldown_days": _("Not again for (days)")}
        help_texts = {"cooldown_days": _("Someone who got it doesn't get it again for this many days.")}
        # The input classes come from core.forms.SiteBoundField.
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": _("We miss you")}),
            "cooldown_days": forms.NumberInput(attrs={"min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["segment"].help_text = _(
            'Tip: a rule like "How the child comes to sessions changed: became At risk in the last 7 days" '
            "makes it a triggered mail."
        )
