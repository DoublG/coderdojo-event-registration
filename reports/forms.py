from django import forms
from django.utils.translation import gettext_lazy as _

from .config import ConfigError, parse


class ReportForm(forms.Form):
    """A report's name and description, and the viewer's settings, which
    the page's script puts in `config` from viewer.save() before posting."""

    name = forms.CharField(label=_("Name"), max_length=200)
    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("What the report shows, for whoever opens it next."),
    )
    config = forms.CharField(widget=forms.HiddenInput, required=False)

    def clean_config(self):
        raw = self.cleaned_data["config"] or "{}"
        try:
            return parse(raw)
        except ConfigError:
            raise forms.ValidationError(_("The report's settings couldn't be read.")) from None
