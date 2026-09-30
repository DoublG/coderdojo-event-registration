import re

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import lazy
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

from core.content_languages import (
    add_translation_fields,
    bound_translation_groups,
    optional_copy,
    save_translation_fields,
)
from dojos.models import Dojo

from .categories import CAN_OPT_OUT, DESCRIPTIONS, MailCategory, categories_for
from .dojo_families import active_since, dojos_of
from .models import Campaign, EmailTemplate, Journey, Segment
from .preferences import muted_dojo_ids, preferences_for


class MailPreferencesForm(forms.Form):
    """One checkbox per category the account can switch off, one per dojo
    whose news reaches the family (on = not muted), plus the mail
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
        # Per dojo: its news, unless muted (DATA_MODEL.md §25). The family's
        # dojos, plus any it muted earlier, so it can always switch one back.
        muted = muted_dojo_ids(user)
        self.dojos = []
        if MailCategory.DOJO_NEWS in self.categories:
            self.dojos = list(
                (dojos_of(user, active_since()) | Dojo.objects.filter(pk__in=muted)).distinct().order_by("name")
            )
        for dojo in self.dojos:
            self.fields[f"dojo_{dojo.pk}"] = forms.BooleanField(
                required=False, label=dojo.name, initial=dojo.pk not in muted
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

    def dojo_fields(self):
        return [self[name] for name in self.fields if name.startswith("dojo_")]

    def dojo_choices(self):
        """(dojo, wants its news) for every dojo, from the cleaned data."""
        return [(dojo, self.cleaned_data[f"dojo_{dojo.pk}"]) for dojo in self.dojos]

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
    # Our own translated text and a reverse()d URL, no user input.
    return mark_safe(  # noqa: S308
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


# --- a dojo's own mail to its families (mailing.dojo_views, DATA_MODEL.md §25) ----


class DojoMailingForm(forms.ModelForm):
    """A dojo mailing: who gets it (one of the prepared audiences, with its
    parameters) and the dojo's text, in its main language plus optional
    versions in its other languages. The audience's parameters are checked
    by mailing.dojo_audiences, which decides what's valid."""

    audience = forms.ChoiceField(label=_("Who gets it"), widget=forms.RadioSelect)
    event = forms.ChoiceField(label=_("Session"), required=False)
    include_waiting_list = forms.BooleanField(label=_("Also the families on its waiting list"), required=False)
    days = forms.TypedChoiceField(label=_("Came in the last"), coerce=int, required=False)
    min_age = forms.IntegerField(label=_("From age"), required=False)
    max_age = forms.IntegerField(label=_("Up to age"), required=False)
    pathway = forms.ChoiceField(label=_("Pathway"), required=False)

    PARAM_FIELDS = ("event", "include_waiting_list", "days", "min_age", "max_age", "pathway")

    class Meta:
        model = Campaign
        fields = ["subject", "message"]
        labels = {"subject": _("Subject"), "message": _("Message")}
        help_texts = {
            "subject": _("Your dojo's name goes in front of it."),
            "message": _("Plain text. Links work; there's no layout, no images and no attachments."),
        }
        widgets = {"message": forms.Textarea(attrs={"rows": 10})}

    def __init__(self, *args, dojo, **kwargs):
        from . import dojo_audiences

        self.dojo = dojo
        kwargs.setdefault("instance", Campaign(dojo=dojo))
        instance = kwargs["instance"]
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("audience", instance.audience or dojo_audiences.ALL_FAMILIES)
        initial.setdefault("days", dojo_audiences.DEFAULT_RECENT_DAYS)
        for name, value in (instance.audience_params or {}).items():
            initial.setdefault(name, value)
        super().__init__(*args, **kwargs)
        self.audiences = dojo_audiences.available(dojo)
        self.fields["audience"].choices = [(a.key, a.label) for a in self.audiences]
        self.fields["event"].choices = [("", _("Pick a session"))] + [
            (e.pk, f"{e.localized('name')} ({timezone.localtime(e.start_time):%d/%m/%Y %H:%M})")
            for e in dojo_audiences.sessions_for(dojo)
        ]
        self.fields["days"].choices = [(d, _("%(days)s days") % {"days": d}) for d in dojo_audiences.RECENT_DAYS]
        self.fields["pathway"].choices = [("", _("Pick a pathway"))] + [
            (p.pk, p.localized("name")) for p in dojo_audiences.pathways_for(dojo)
        ]
        for name in ("min_age", "max_age"):
            self.fields[name].min_value = dojo_audiences.MIN_AGE
            self.fields[name].max_value = dojo_audiences.MAX_AGE
        self.fields["subject"].required = True
        self.fields["message"].required = True
        self.fields["message"].max_length = settings.MAILING_DOJO_MESSAGE_MAX_LENGTH
        self.fields["message"].widget.attrs["maxlength"] = settings.MAILING_DOJO_MESSAGE_MAX_LENGTH
        self.translation_groups = bound_translation_groups(
            self,
            add_translation_fields(
                self, self.instance, lambda field: optional_copy(self.fields[field], self.fields[field].label)
            ),
        )

    def audience_options(self):
        """Per audience: its radio value, label, description, whether it's
        picked, whether it needs the child-data consent, and its fields."""
        picked = str(self["audience"].value() or "")
        return [
            {
                "key": a.key,
                "label": a.label,
                "description": a.description,
                "checked": a.key == picked,
                "needs_consent": a.needs_consent,
                "fields": [self[name] for name in self.PARAM_FIELDS if name in _param_fields(a)],
            }
            for a in self.audiences
        ]

    def raw_params(self):
        return {name: self.cleaned_data.get(name) for name in self.PARAM_FIELDS}

    def clean(self):
        from . import dojo_audiences

        cleaned = super().clean()
        if cleaned.get("audience"):
            try:
                self.params = dojo_audiences.clean_params(cleaned["audience"], self.dojo, self.raw_params())
            except dojo_audiences.DojoAudienceError as error:
                self.add_error("audience", str(error))
        return cleaned

    def save(self, commit=True):
        from . import dojo_audiences

        audience = dojo_audiences.get(self.cleaned_data["audience"])
        campaign = super().save(commit=False)
        campaign.dojo = self.dojo
        campaign.category = audience.category
        campaign.template_key = audience.template
        campaign.name = campaign.subject[:200]
        campaign.audience = self.cleaned_data["audience"]
        campaign.audience_params = self.params
        save_translation_fields(self, campaign)
        if commit:
            campaign.save()
        return campaign


def _param_fields(audience):
    """The form fields for an audience's parameters (event for a session,
    min_age/max_age for an age range, ...)."""
    names = set(audience.params)
    if "min_age" in names:
        names.add("max_age")
    return names
