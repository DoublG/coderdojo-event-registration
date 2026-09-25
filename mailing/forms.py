from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from geo.models import Municipality

from .categories import CAN_OPT_OUT, DESCRIPTIONS, categories_for
from .preferences import preferences_for


class MailPreferencesForm(forms.Form):
    """One checkbox per category the account can switch off, plus the mail
    language and (adults) the postcode. Categories that can't be switched
    off are listed by the template, not as fields."""

    preferred_language = forms.ChoiceField(
        label="Language for emails", choices=settings.LANGUAGES,
        widget=forms.Select(attrs={"class": "cd-form__select body"}),
    )
    postal_code = forms.CharField(
        label="Postcode", required=False, max_length=4,
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "inputmode": "numeric", "placeholder": "9000"}),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        current = preferences_for(user)
        kwargs.setdefault("initial", {}).update({
            "preferred_language": user.preferred_language or settings.LANGUAGES[0][0],
            "postal_code": user.postal_code,
            **{f"category_{category}": subscribed for category, subscribed in current.items()},
        })
        super().__init__(*args, **kwargs)
        self.categories = categories_for(user)
        for category in self.categories:
            if CAN_OPT_OUT[category]:
                self.fields[f"category_{category}"] = forms.BooleanField(
                    required=False, label=category.label, help_text=DESCRIPTIONS[category],
                )
        if user.is_ninja:
            del self.fields["postal_code"]

    def clean_postal_code(self):
        postal_code = self.cleaned_data["postal_code"].strip()
        if postal_code and not Municipality.objects.filter(postal_code=postal_code).exists():
            raise ValidationError("That isn't a Belgian postcode we know.")
        return postal_code

    def category_fields(self):
        return [self[name] for name in self.fields if name.startswith("category_")]

    def always_on(self):
        return [(category.label, DESCRIPTIONS[category]) for category in self.categories if not CAN_OPT_OUT[category]]

    def chosen(self):
        """{category: subscribed} from the submitted checkboxes."""
        return {name.removeprefix("category_"): value for name, value in self.cleaned_data.items()
                if name.startswith("category_")}
