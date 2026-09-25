from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from content.models import Announcement
from core.content_languages import (
    add_translation_fields,
    bound_translation_groups,
    clean_languages,
    optional_copy,
    save_translation_fields,
)
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
        choices=[(NO_TEMPLATE_ICON, _("No template — I'll upload my own below"))] + TEMPLATE_ICONS,
        widget=forms.RadioSelect,
    )

    # The dojo's languages (Dojo.languages): the ones its sessions are given
    # in and its texts are written in; the main one comes first.
    languages = forms.MultipleChoiceField(
        label=_("Languages"), choices=settings.LANGUAGES, widget=forms.CheckboxSelectMultiple, required=False,
    )
    main_language = forms.ChoiceField(
        label=_("Main language"), choices=settings.LANGUAGES, required=False,
        widget=forms.Select(attrs={"class": "cd-form__select body"}),
    )

    TRANSLATION_LABELS = {
        "tagline": _("Tagline"), "description": _("Description"),
        "schedule_description": _("Meets"), "visit_notes": _("Extra info"),
    }

    class Meta:
        model = Dojo
        fields = [
            "name", "icon", "tagline", "description",
            "schedule_description", "min_age", "max_age",
            "email", "phone", "municipality", "address", "visit_notes", "pathways",
        ]
        widgets = {
            "pathways": forms.CheckboxSelectMultiple,
            "name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("CoderDojo Ghent")}),
            "icon": forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
            "tagline": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 2,
                "placeholder": _("A short line shown right under the dojo's name."),
            }),
            "description": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 6,
                "placeholder": _("Shown further down the page, above the team — what makes this dojo worth joining."),
            }),
            "schedule_description": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("e.g. Every 2nd Saturday")}),
            "min_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": _("7")}),
            "max_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": _("18")}),
            "email": forms.EmailInput(attrs={"class": "cd-form__input body", "placeholder": _("hello@example.org")}),
            "phone": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("+32 4xx xx xx xx")}),
            "municipality": forms.Select(attrs={"class": "cd-form__select body"}),
            "address": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("Street, number, postcode, city")}),
            "visit_notes": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 4,
                "placeholder": _("Parking, entrance, accessibility — anything extra for the Visit us section."),
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["municipality"].queryset = self.fields["municipality"].queryset.order_by("name")
        self.fields["municipality"].empty_label = _("Not set")
        self.fields["template_icon"].initial = library_filename(self.instance.icon, "dojos") or NO_TEMPLATE_ICON
        languages = self.instance.content_languages()
        self.fields["languages"].initial = languages
        self.fields["main_language"].initial = languages[0]
        # A field per text in each of the dojo's other (saved) languages.
        self.translation_groups = bound_translation_groups(self, add_translation_fields(
            self, self.instance, lambda field: optional_copy(self.fields[field], self.TRANSLATION_LABELS[field]),
        ))

    def clean(self):
        cleaned_data = super().clean()
        # A post without these fields (an older form, a script) keeps the
        # dojo's languages as they are.
        main = cleaned_data.get("main_language")
        chosen = cleaned_data.get("languages") or []
        if not main:
            cleaned_data["languages"] = None
        else:
            # The main language is always one of them, and always first.
            cleaned_data["languages"] = clean_languages([main] + [code for code, _name in settings.LANGUAGES if code in chosen])
        return cleaned_data

    def save(self, commit=True):
        dojo = super().save(commit=False)
        save_translation_fields(self, dojo)
        if self.cleaned_data.get("languages"):
            dojo.languages = self.cleaned_data["languages"]
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
            "placeholder": _("Enter your postcode or city"),
        }),
    )
    # Set by the "Use my location" button via the browser Geolocation API
    # (see dojo_list.html's extra_script), bypassing the location field's
    # text geocoding entirely once present.
    lat = forms.FloatField(required=False, widget=forms.HiddenInput())
    lon = forms.FloatField(required=False, widget=forms.HiddenInput())
    # Only dojos (or sessions) given in this language (Dojo.languages).
    language = forms.ChoiceField(
        required=False,
        choices=[("", _("Any language"))] + list(settings.LANGUAGES),
        widget=forms.Select(attrs={"class": "cd-form__select body", "id": "dojo-language", "aria-label": _("Language")}),
    )


class DojoCreateForm(forms.ModelForm):
    """What an approved champion fills in to create a dojo (dojos.views.
    dojo_create): just enough to identify it. It starts as a draft; the rest
    of the profile is filled in on the Settings page before launching."""

    class Meta:
        model = Dojo
        fields = ["name", "address", "email"]
        labels = {"name": _("Name"), "address": _("Address"), "email": _("Email")}
        widgets = {
            "name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("e.g. CoderDojo Leuven")}),
            "address": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("Street and number, postcode, city")}),
            "email": forms.EmailInput(attrs={"class": "cd-form__input body", "placeholder": _("hello@yourdojo.example")}),
        }


class AnnouncementForm(forms.ModelForm):
    """One "From this dojo" update (dojos.views.dojo_updates). Dated the
    day it's posted; the team writes only the text."""

    def __init__(self, *args, dojo, **kwargs):
        kwargs.setdefault("instance", Announcement(dojo=dojo))
        super().__init__(*args, **kwargs)
        # The same update in the dojo's other languages (optional).
        self.translation_groups = bound_translation_groups(self, add_translation_fields(
            self, self.instance, lambda field: optional_copy(self.fields[field], _("Update")),
        ))

    def save(self, commit=True):
        announcement = super().save(commit=False)
        save_translation_fields(self, announcement)
        if commit:
            announcement.save()
        return announcement

    class Meta:
        model = Announcement
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 3, "maxlength": 500,
                "placeholder": _("e.g. We've moved to the bigger room from October, same time, same entrance."),
            }),
        }
        labels = {"text": _("New update")}

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if len(text) > 500:
            raise forms.ValidationError(_("Keep it short: 500 characters at most."))
        return text
