from django import forms

from .models import Dojo


class DojoProfileForm(forms.ModelForm):
    """Everything a dojo owner can edit on their own dojo's public profile
    (dojos/dojo_detail.html) — see dojos.views.dojo_manage. Deliberately
    excludes owner/location/province: location is derived from address via
    geocoding on save (see dojo_manage), province from location (see
    geo.geocoding.find_province), and owner is never self-service."""

    class Meta:
        model = Dojo
        fields = [
            "name", "icon", "tagline", "description",
            "schedule_description", "min_age", "max_age",
            "email", "phone", "municipality", "address", "visit_notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "CoderDojo Ghent"}),
            "icon": forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
            "tagline": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 2,
                "placeholder": "A short line shown right under the dojo's name.",
            }),
            "description": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 6,
                "placeholder": "Shown further down the page, above the team — what makes this dojo worth joining.",
            }),
            "schedule_description": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "e.g. Every 2nd Saturday"}),
            "min_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": "7"}),
            "max_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": "18"}),
            "email": forms.EmailInput(attrs={"class": "cd-form__input body", "placeholder": "hello@example.org"}),
            "phone": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "+32 4xx xx xx xx"}),
            "municipality": forms.Select(attrs={"class": "cd-form__select body"}),
            "address": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Street, number, postcode, city"}),
            "visit_notes": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 4,
                "placeholder": "Parking, entrance, accessibility — anything extra for the Visit us section.",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["municipality"].queryset = self.fields["municipality"].queryset.order_by("name")
        self.fields["municipality"].empty_label = "Not set"


class DojoSearchForm(forms.Form):
    location = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={
            "class": "cd-dojo-finder__input body",
            "placeholder": "Enter your postcode or city",
        }),
    )
    # Set by the "Use my location" button via the browser Geolocation API
    # (see dojo_list.html's extra_script), bypassing the location field's
    # text geocoding entirely once present.
    lat = forms.FloatField(required=False, widget=forms.HiddenInput())
    lon = forms.FloatField(required=False, widget=forms.HiddenInput())
