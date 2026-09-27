from django import forms
from django.utils.translation import gettext_lazy as _

from .models import DojoApiClient


class ApiClientForm(forms.Form):
    """A new API client on the dojo's API page (api.views.dojo_api_clients).
    What makes a valid client lives in api.services.create_client; its
    ApiClientError becomes the form's error."""

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
        choices=DojoApiClient.SCOPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        initial=[value for value, _label in DojoApiClient.SCOPE_CHOICES],
    )
