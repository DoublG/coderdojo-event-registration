from django import forms


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
