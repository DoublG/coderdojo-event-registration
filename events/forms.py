from datetime import datetime

from django import forms
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.content_languages import (
    add_translation_fields,
    bound_translation_groups,
    optional_copy,
    save_translation_fields,
)
from core.image_library import library_filename, use_library_image
from dojos.models import Dojo
from pathways.models import Pathway

from .models import Event
from .template_images import TEMPLATE_IMAGES

DATE_ANY = ""
DATE_WEEK = "week"
DATE_MONTH = "month"

AGE_ANY = ""
AGE_RANGES = {
    "7-9": (7, 9),
    "10-13": (10, 13),
    "14-18": (14, 18),
}


class EventSearchForm(forms.Form):
    dojo = forms.ModelChoiceField(
        queryset=Dojo.objects.public().order_by("name"),
        required=False,
        empty_label=_("All dojos"),
        widget=forms.Select(attrs={"class": "cd-form__select body", "id": "ep-dojo"}),
    )
    location = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "id": "ep-location", "placeholder": _("Postcode or city")}),
    )
    date = forms.ChoiceField(
        required=False,
        choices=[(DATE_ANY, _("Any date")), (DATE_WEEK, _("This week")), (DATE_MONTH, _("This month"))],
        widget=forms.Select(attrs={"class": "cd-form__select body", "id": "ep-date"}),
    )
    # Only dojos (or sessions) given in this language (Dojo.languages).
    language = forms.ChoiceField(
        required=False,
        choices=[("", _("Any language"))] + list(settings.LANGUAGES),
        widget=forms.Select(attrs={"class": "cd-form__select body", "id": "ep-language"}),
    )
    age = forms.ChoiceField(
        required=False,
        choices=[(AGE_ANY, _("All ages"))] + [(key, key.replace("-", "–")) for key in AGE_RANGES],
        widget=forms.Select(attrs={"class": "cd-form__select body", "id": "ep-age"}),
    )


# Belgium's own date/time notation — day before month, 24-hour clock — used
# for EventForm's date/start_time/end_time fields regardless of the
# visitor's own browser/OS locale (a native <input type="date"> can't be
# forced to a fixed display order, so these are plain text fields instead).
BELGIAN_DATE_FORMAT = "%d/%m/%Y"
BELGIAN_TIME_FORMAT = "%H:%M"

NO_TEMPLATE_IMAGE = ""


class EventForm(forms.ModelForm):
    """A dojo owner creating or editing a session on their own admin
    dashboard — see dojos.views.dojo_event_create/dojo_event_detail. Status
    isn't a field here: new events always start out Draft (Event.status'
    model default), and any later change (publish, close, reopen, back to
    draft) is its own deliberate action via dojos.views.dojo_event_set_status.

    A session is always a single day: rather than two separate start/end
    *datetime* pickers (which could disagree on the date), this form has
    one date field plus separate start/end *time* fields, both applied to
    that same date in save() — spanning midnight simply isn't
    representable through this form."""

    event_date = forms.DateField(
        input_formats=[BELGIAN_DATE_FORMAT],
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("dd/mm/yyyy"), "inputmode": "numeric"}),
    )
    start_time = forms.TimeField(
        input_formats=[BELGIAN_TIME_FORMAT],
        widget=forms.TimeInput(
            attrs={"class": "cd-form__input body", "type": "time", "step": "60", "placeholder": _("HH:MM")},
            format=BELGIAN_TIME_FORMAT,
        ),
    )
    end_time = forms.TimeField(
        input_formats=[BELGIAN_TIME_FORMAT],
        widget=forms.TimeInput(
            attrs={"class": "cd-form__input body", "type": "time", "step": "60", "placeholder": _("HH:MM")},
            format=BELGIAN_TIME_FORMAT,
        ),
    )
    # Not a model field — a shortcut that, on save(), points `image` at one
    # of the standard event banners (core.image_library, no copy made)
    # instead of requiring an upload. An uploaded file (see save()) always
    # wins over this if both are somehow submitted at once.
    template_image = forms.ChoiceField(
        required=False,
        choices=[(NO_TEMPLATE_IMAGE, _("No template — I'll upload my own below"))] + TEMPLATE_IMAGES,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Event
        fields = [
            "name", "places", "external_registration_url", "venue_name", "image",
            "description", "min_age", "max_age", "audience", "team", "pathways",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("Coding Saturday")}),
            "places": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": _("20")}),
            "external_registration_url": forms.URLInput(attrs={
                "class": "cd-form__input body", "placeholder": _("https://www.coolestprojects.org/…"),
            }),
            "venue_name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _('e.g. "Ghent Public Library"')}),
            "image": forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
            "description": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 6,
                "placeholder": _("What this session is about, what to bring — shown on the session's public page."),
            }),
            "min_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": _("7")}),
            "max_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": _("18")}),
            "audience": forms.Select(attrs={"class": "cd-form__select body"}),
            "team": forms.CheckboxSelectMultiple,
            "pathways": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, dojo, **kwargs):
        super().__init__(*args, **kwargs)
        # Not sent (an older form, a script): keep the model default.
        self.fields["audience"].required = False
        # Only the organisation's own events (an organisation dojo, DATA_MODEL.md
        # §12) may take registrations on another website; for those, places
        # are optional.
        if dojo.is_organisation:
            self.fields["places"].required = False
        else:
            del self.fields["external_registration_url"]
        # Who runs this session: anyone active on the dojo's team (champion,
        # mentors and youth mentors), shown as "Name (Role)".
        self.fields["team"].queryset = dojo.memberships.active().select_related("user").order_by("user__first_name")
        self.fields["team"].label_from_instance = lambda m: f"{m.name} ({m.get_role_display()})"
        # A new session pre-selects the pathways its dojo provides; the team
        # can still pick any pathway for this particular session.
        self.fields["pathways"].queryset = Pathway.objects.order_by("name")
        self.fields["pathways"].label_from_instance = lambda pathway: pathway.localized("name")
        if not self.instance.pk:
            self.fields["pathways"].initial = list(dojo.pathways.values_list("pk", flat=True))
        self.fields["template_image"].initial = library_filename(self.instance.image, "events") or NO_TEMPLATE_IMAGE
        if self.instance.pk:
            self.fields["event_date"].initial = self.instance.start_time.date()
            self.fields["start_time"].initial = self.instance.start_time.time()
            self.fields["end_time"].initial = self.instance.end_time.time()
        # The session's name and description in the dojo's other languages.
        labels = {"name": _("Name"), "description": _("Description")}
        self.translation_groups = bound_translation_groups(self, add_translation_fields(
            self, self.instance, lambda field: optional_copy(self.fields[field], labels[field]),
        ))

    def clean_audience(self):
        return self.cleaned_data.get("audience") or Event.EVERYONE

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and end_time and end_time <= start_time:
            self.add_error("end_time", _("End time must be after the start time."))
        if "places" not in self.errors and cleaned_data.get("places") is None:
            if cleaned_data.get("external_registration_url"):
                cleaned_data["places"] = 0
            else:
                self.add_error("places", _("This field is required."))
        return cleaned_data

    def save(self, commit=True):
        event = super().save(commit=False)
        event_date = self.cleaned_data["event_date"]
        event.start_time = timezone.make_aware(datetime.combine(event_date, self.cleaned_data["start_time"]))
        event.end_time = timezone.make_aware(datetime.combine(event_date, self.cleaned_data["end_time"]))

        template_image = self.cleaned_data.get("template_image")
        if template_image and not self.files.get("image"):
            use_library_image(event, "image", "events", template_image)
        save_translation_fields(self, event)

        if commit:
            event.save()
            self.save_m2m()
        return event
