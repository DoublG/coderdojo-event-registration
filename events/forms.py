from django import forms

from dojos.models import Dojo

from .models import Event

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
        queryset=Dojo.objects.order_by("name"),
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


DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"


class EventForm(forms.ModelForm):
    """A dojo owner creating a session on their own admin dashboard — see
    dojos.views.dojo_event_create. New events always start out Draft
    (Event.status' model default): the "Open" state that makes a session
    live for registration is a deliberate follow-up action from the
    events list, not something chosen here — matches the "closed" state,
    which is only ever a manual action too (see dojos.views.dojo_event_set_status)."""

    class Meta:
        model = Event
        fields = [
            "name", "start_time", "end_time", "places", "venue_name", "image",
            "description", "min_age", "max_age", "mentor",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Coding Saturday"}),
            "start_time": forms.DateTimeInput(
                attrs={"class": "cd-form__input body", "type": "datetime-local"}, format=DATETIME_LOCAL_FORMAT,
            ),
            "end_time": forms.DateTimeInput(
                attrs={"class": "cd-form__input body", "type": "datetime-local"}, format=DATETIME_LOCAL_FORMAT,
            ),
            "places": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": "20"}),
            "venue_name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": 'e.g. "Ghent Public Library"'}),
            "image": forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
            "description": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 6,
                "placeholder": "What this session is about, what to bring — shown on the session's public page.",
            }),
            "min_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": "7"}),
            "max_age": forms.NumberInput(attrs={"class": "cd-form__input body", "placeholder": "18"}),
            "mentor": forms.Select(attrs={"class": "cd-form__select body"}),
        }

    def __init__(self, *args, dojo, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_time"].input_formats = [DATETIME_LOCAL_FORMAT]
        self.fields["end_time"].input_formats = [DATETIME_LOCAL_FORMAT]
        self.fields["mentor"].queryset = dojo.mentors.order_by("name")
        self.fields["mentor"].empty_label = "Not set"

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and end_time and end_time <= start_time:
            self.add_error("end_time", "End time must be after the start time.")
        return cleaned_data
