from django import forms
from django.utils import timezone

from events.models import Event

from .models import Promotion

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


def _datetime_input():
    return forms.DateTimeInput(attrs={"class": "cd-form__input body", "type": "datetime-local"}, format=DATETIME_FORMAT)


class PromotionForm(forms.ModelForm):
    """A promotion on the organisation dashboard (content.manage). Any
    upcoming event can be picked, drafts included, so a promotion can be
    prepared before its event is published: it only shows once the public
    site shows the event (Promotion.objects.showing)."""

    class Meta:
        model = Promotion
        fields = ["event", "placement", "rank", "starts_at", "ends_at", "title", "text", "image"]
        widgets = {
            "event": forms.Select(attrs={"class": "cd-form__select body"}),
            "placement": forms.Select(attrs={"class": "cd-form__select body"}),
            "rank": forms.NumberInput(attrs={"class": "cd-form__input body", "min": 0}),
            "starts_at": _datetime_input(),
            "ends_at": _datetime_input(),
            "title": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Leave empty to use the event's name"}),
            "text": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Show your project to the world!"}),
            "image": forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = [DATETIME_FORMAT]
        self.fields["starts_at"].label = "Show from"
        self.fields["ends_at"].label = "Show until"
        upcoming = Event.objects.filter(end_time__gt=timezone.now())
        if self.instance.event_id:
            upcoming = upcoming | Event.objects.filter(pk=self.instance.event_id)
        self.fields["event"].queryset = upcoming.order_by("start_time")
        self.fields["event"].label_from_instance = _event_label


def _event_label(event):
    label = f"{event.name} — {event.dojo.name}, {timezone.localtime(event.start_time):%d/%m/%Y %H:%M}"
    return f"{label} (draft)" if event.status == Event.DRAFT else label
