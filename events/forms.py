from datetime import datetime

from django import forms
from django.utils import timezone

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
        empty_label="All dojos",
        widget=forms.Select(attrs={"class": "cd-form__select body", "id": "ep-dojo"}),
    )
    location = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "id": "ep-location", "placeholder": "Postcode or city"}),
    )
    date = forms.ChoiceField(
        required=False,
        choices=[(DATE_ANY, "Any date"), (DATE_WEEK, "This week"), (DATE_MONTH, "This month")],
        widget=forms.Select(attrs={"class": "cd-form__select body", "id": "ep-date"}),
    )
    age = forms.ChoiceField(
        required=False,
        choices=[(AGE_ANY, "All ages")] + [(key, key.replace("-", "–")) for key in AGE_RANGES],
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
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "dd/mm/yyyy", "inputmode": "numeric"}),
    )
    start_time = forms.TimeField(
        input_formats=[BELGIAN_TIME_FORMAT],
        widget=forms.TimeInput(
            attrs={"class": "cd-form__input body", "type": "time", "step": "60", "placeholder": "HH:MM"},
            format=BELGIAN_TIME_FORMAT,
        ),
    )
    end_time = forms.TimeField(
        input_formats=[BELGIAN_TIME_FORMAT],
        widget=forms.TimeInput(
            attrs={"class": "cd-form__input body", "type": "time", "step": "60", "placeholder": "HH:MM"},
            format=BELGIAN_TIME_FORMAT,
        ),
    )
    # Not a model field — a shortcut that, on save(), points `image` at one
    # of the standard event banners (core.image_library, no copy made)
    # instead of requiring an upload. An uploaded file (see save()) always
    # wins over this if both are somehow submitted at once.
    template_image = forms.ChoiceField(
        required=False,
        choices=[(NO_TEMPLATE_IMAGE, "No template — I'll upload my own below")] + TEMPLATE_IMAGES,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Event
        fields = [
            "name", "places", "venue_name", "image",
            "description", "min_age", "max_age", "audience", "team", "pathways",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Coding Saturday"}),
            "places": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": "20"}),
            "venue_name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": 'e.g. "Ghent Public Library"'}),
            "image": forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
            "description": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 6,
                "placeholder": "What this session is about, what to bring — shown on the session's public page.",
            }),
            "min_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": "7"}),
            "max_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": "18"}),
            "audience": forms.Select(attrs={"class": "cd-form__select body"}),
            "team": forms.CheckboxSelectMultiple,
            "pathways": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, dojo, **kwargs):
        super().__init__(*args, **kwargs)
        # Not sent (an older form, a script): keep the model default.
        self.fields["audience"].required = False
        # Who runs this session: anyone active on the dojo's team (champion,
        # mentors and youth mentors), shown as "Name (Role)".
        self.fields["team"].queryset = dojo.memberships.active().select_related("user").order_by("user__first_name")
        self.fields["team"].label_from_instance = lambda m: f"{m.name} ({m.get_role_display()})"
        # A new session pre-selects the pathways its dojo provides; the team
        # can still pick any pathway for this particular session.
        self.fields["pathways"].queryset = Pathway.objects.order_by("name")
        if not self.instance.pk:
            self.fields["pathways"].initial = list(dojo.pathways.values_list("pk", flat=True))
        self.fields["template_image"].initial = library_filename(self.instance.image, "events") or NO_TEMPLATE_IMAGE
        if self.instance.pk:
            self.fields["event_date"].initial = self.instance.start_time.date()
            self.fields["start_time"].initial = self.instance.start_time.time()
            self.fields["end_time"].initial = self.instance.end_time.time()

    def clean_audience(self):
        return self.cleaned_data.get("audience") or Event.EVERYONE

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and end_time and end_time <= start_time:
            self.add_error("end_time", "End time must be after the start time.")
        return cleaned_data

    def save(self, commit=True):
        event = super().save(commit=False)
        event_date = self.cleaned_data["event_date"]
        event.start_time = timezone.make_aware(datetime.combine(event_date, self.cleaned_data["start_time"]))
        event.end_time = timezone.make_aware(datetime.combine(event_date, self.cleaned_data["end_time"]))

        template_image = self.cleaned_data.get("template_image")
        if template_image and not self.files.get("image"):
            use_library_image(event, "image", "events", template_image)

        if commit:
            event.save()
            self.save_m2m()
        return event
