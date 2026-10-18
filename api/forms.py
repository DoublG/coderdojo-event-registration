from datetime import date, datetime, time, timedelta

from django import forms
from django.utils.translation import gettext_lazy as _

from events.models import Event
from events.services import PlannedSession

from .models import DojoApiClient

# What the champion sees for each scope on the dojo's API page.
SCOPE_LABELS = {
    DojoApiClient.READ: _("See the sessions and who has a place"),
    DojoApiClient.WRITE: _("Mark who came"),
    DojoApiClient.EVENTS_READ: _("See the sessions"),
    DojoApiClient.EVENTS_WRITE: _("Plan sessions: add and change them, e.g. from a spreadsheet"),
}


class ApiClientForm(forms.Form):
    """A new API client on the dojo's API page (api.views.dojo_api_clients).
    What makes a valid client lives in api.services.create_client; its
    ApiClientError becomes the form's error. No scope is ticked to start
    with: the champion gives a client only what it needs."""

    name = forms.CharField(
        label=_("Name"),
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": _("Scan app at the door"), "required": True}),
    )
    # Rendered by the page itself: each scope with its description.
    scope = forms.MultipleChoiceField(
        label=_("What it may do"),
        required=False,
        choices=[(value, SCOPE_LABELS[value]) for value, _label in DojoApiClient.SCOPE_CHOICES],
        widget=forms.CheckboxSelectMultiple,
    )


# Excel counts days from 30 December 1899 (its serial date numbers), and
# keeps a time of day as a fraction of a day.
EXCEL_EPOCH = date(1899, 12, 30)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class SpreadsheetDateField(forms.DateField):
    """A date as text (2026-09-26, or 26/09/2026) or as Excel's serial number."""

    input_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]

    def to_python(self, value):
        number = _number(value)
        if number is not None and number >= 1:
            return EXCEL_EPOCH + timedelta(days=int(number))
        return super().to_python(value)


class SpreadsheetTimeField(forms.TimeField):
    """A time as text (14:00, or 14:00:00) or as Excel's fraction of a day."""

    input_formats = ["%H:%M", "%H:%M:%S"]

    def to_python(self, value):
        number = _number(value)
        if number is not None and 0 <= number < 1:
            minutes = round(number * 24 * 60)
            return time(minutes // 60, minutes % 60)
        return super().to_python(value)


class PlannedSessionForm(forms.Form):
    """One row of `POST /api/v1/events/sync` (api.v1), checked on its own so
    one bad row never stops the others. The session's own rules (times,
    places, ages, not in the past) are events.services'. Every field is
    sent on every sync: a blank cell clears the venue or an age, a blank
    status keeps the session's status (a new session starts as a draft)."""

    external_ref = forms.CharField(label="external_ref", max_length=100)
    name = forms.CharField(label="name", max_length=200)
    date = SpreadsheetDateField(label="date")
    start_time = SpreadsheetTimeField(label="start_time")
    end_time = SpreadsheetTimeField(label="end_time")
    places = forms.IntegerField(label="places")
    venue_name = forms.CharField(label="venue_name", max_length=200, required=False)
    min_age = forms.IntegerField(label="min_age", min_value=0, max_value=99, required=False)
    max_age = forms.IntegerField(label="max_age", min_value=0, max_value=99, required=False)
    audience = forms.ChoiceField(label="audience", choices=Event.AUDIENCE_CHOICES, required=False)
    status = forms.ChoiceField(label="status", choices=Event.STATUS_CHOICES, required=False)

    def problems(self):
        """The row's errors as one line, each with its field's name."""
        return " ".join(
            f"{field}: {' '.join(messages)}" if field != "__all__" else " ".join(messages)
            for field, messages in self.errors.items()
        )

    def session(self):
        data = self.cleaned_data
        return PlannedSession(
            external_ref=data["external_ref"],
            name=data["name"],
            date=data["date"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            places=data["places"],
            venue_name=data["venue_name"],
            min_age=data["min_age"],
            max_age=data["max_age"],
            audience=data["audience"] or Event.EVERYONE,
            status=data["status"],
        )


def cell(value):
    """A spreadsheet cell as form data: Excel sends every number as a
    decimal, so 12.0 is 12 (also in a key such as 202612)."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value).strip()
