from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.content_languages import (
    add_translation_fields,
    bound_translation_groups,
    optional_copy,
    save_translation_fields,
)
from events.models import Event

from .models import Promotion, Sponsor

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
            "title": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("Leave empty to use the event's name")}),
            "text": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("Show your project to the world!")}),
            "image": forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = [DATETIME_FORMAT]
        self.fields["starts_at"].label = _("Show from")
        self.fields["ends_at"].label = _("Show until")
        self.fields["ends_at"].help_text = _("Empty: the promotion ends when the event starts.")
        self.fields["rank"].help_text = _("Lower shows first within a placement.")
        self.fields["image"].help_text = _("Optional: replaces the event's banner.")
        # The title and pitch in the organisation's other languages.
        labels = {"title": _("Title"), "text": _("Short pitch")}
        self.translation_groups = bound_translation_groups(self, add_translation_fields(
            self, self.instance, lambda field: optional_copy(self.fields[field], labels[field]),
        ))
        upcoming = Event.objects.filter(end_time__gt=timezone.now())
        if self.instance.event_id:
            upcoming = upcoming | Event.objects.filter(pk=self.instance.event_id)
        self.fields["event"].queryset = upcoming.order_by("start_time")
        self.fields["event"].label_from_instance = _event_label

    def save(self, commit=True):
        promotion = super().save(commit=False)
        save_translation_fields(self, promotion)
        if commit:
            promotion.save()
            self.save_m2m()
        return promotion


def _event_label(event):
    label = f"{event.name} — {event.dojo.name}, {timezone.localtime(event.start_time):%d/%m/%Y %H:%M}"
    return _("%(label)s (draft)") % {"label": label} if event.status == Event.DRAFT else label


class SponsorForm(forms.ModelForm):
    """One sponsor on the organisation dashboard's Sponsors page."""

    class Meta:
        model = Sponsor
        fields = ["name", "url", "logo", "order", "is_public"]
        labels = {"name": _("Name"), "url": _("Website"), "logo": _("Logo"), "order": _("Order"), "is_public": _("Shown on the homepage")}
        help_texts = {"logo": _("Optional. Without a logo, the sponsor's name is shown."), "order": _("Lower comes first.")}
        widgets = {
            "name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": _("e.g. Telenet")}),
            "url": forms.URLInput(attrs={"class": "cd-form__input body", "placeholder": "https://"}),
            "logo": forms.ClearableFileInput(attrs={"class": "cd-form__input body", "accept": "image/*"}),
            "order": forms.NumberInput(attrs={"class": "cd-form__input body", "min": 0}),
        }

