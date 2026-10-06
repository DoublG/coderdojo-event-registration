from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from dojos.models import Dojo

from .categories import CAN_OPT_OUT, DESCRIPTIONS, MailCategory, categories_for
from .dojo_families import active_since, dojos_of
from .models import EmailSuppression, EmailTemplate
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


class BlockAddressForm(forms.Form):
    """Block an address by hand, on the Mail queue page (mailing.queue_actions.block)."""

    email = forms.EmailField(label=_("Email address"))
    note = forms.CharField(
        label=_("Why"),
        required=False,
        max_length=255,
        help_text=_('Only the organisation sees this, e.g. "The family asked us to stop".'),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if EmailSuppression.objects.filter(email=email).exists():
            raise ValidationError(_("%(email)s is already blocked.") % {"email": email})
        return email
