from django import forms

from dojos.models import Dojo

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
