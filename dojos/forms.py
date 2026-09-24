from django import forms

from core.image_library import library_filename, use_library_image

from .models import Dojo
from .template_icons import TEMPLATE_ICONS

NO_TEMPLATE_ICON = ""


class DojoProfileForm(forms.ModelForm):
    """Everything a dojo owner can edit on their own dojo's public profile
    (dojos/dojo_detail.html) — see dojos.views.dojo_manage. Deliberately
    excludes owner/location/province: location is derived from address via
    geocoding on save (see dojo_manage), province from location (see
    geo.geocoding.find_province), and owner is never self-service.

    dojo_manage always calls save(commit=False) itself (it still has its
    own dojo.save() to do afterwards, once the address/geocoding fields
    are settled) — save() below still works with that: the template_icon
    link just sets a pending value on the instance's `icon` field, same as
    any other field, for whichever save() call actually commits it."""

    # Not a model field — a shortcut that, on save(), points `icon` at one
    # of the standard dojo icons (core.image_library, no copy made) instead
    # of requiring an upload. An uploaded file (see save()) always wins
    # over this if both are somehow submitted at once.
    template_icon = forms.ChoiceField(
        required=False,
        choices=[(NO_TEMPLATE_ICON, "No template — I'll upload my own below")] + TEMPLATE_ICONS,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Dojo
        fields = [
            "name", "icon", "tagline", "description",
            "schedule_description", "min_age", "max_age",
            "email", "phone", "municipality", "address", "visit_notes", "pathways",
        ]
        widgets = {
            "pathways": forms.CheckboxSelectMultiple,
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
        self.fields["template_icon"].initial = library_filename(self.instance.icon, "dojos") or NO_TEMPLATE_ICON

    def save(self, commit=True):
        dojo = super().save(commit=False)
        template_icon = self.cleaned_data.get("template_icon")
        if template_icon and not self.files.get("icon"):
            use_library_image(dojo, "icon", "dojos", template_icon)
        if commit:
            dojo.save()
        return dojo


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


class DojoCreateForm(forms.ModelForm):
    """What an approved champion fills in to create a dojo (dojos.views.
    dojo_create): just enough to identify it. It starts as a draft; the rest
    of the profile is filled in on the Settings page before launching."""

    class Meta:
        model = Dojo
        fields = ["name", "address", "email"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "e.g. CoderDojo Leuven"}),
            "address": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Street and number, postcode, city"}),
            "email": forms.EmailInput(attrs={"class": "cd-form__input body", "placeholder": "hello@yourdojo.example"}),
        }
