from django import forms
from django.utils.translation import gettext_lazy as _

from .config import ConfigError, parse
from .models import Report


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
    status = forms.ChoiceField(
        label=_("Status"),
        choices=Report.STATUS_CHOICES,
        initial=Report.DRAFT,
        help_text=_("A draft is only for the organisation's admins."),
    )
    shared_with_dojos = forms.BooleanField(
        label=_("Share with the dojos"),
        required=False,
        help_text=_("Once published, every dojo's champion sees it on their own dojo's figures, read-only."),
    )
    position = forms.IntegerField(
        label=_("Order"),
        min_value=0,
        initial=0,
        required=False,
        help_text=_("Where it comes on the dojos' Reports page: lowest first."),
    )
    config = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, shareable=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not shareable:
            # A dataset without a dojo column can't be shown per dojo.
            del self.fields["shared_with_dojos"]

    def clean_config(self):
        raw = self.cleaned_data["config"] or "{}"
        try:
            return parse(raw)
        except ConfigError:
            raise forms.ValidationError(_("The report's settings couldn't be read.")) from None
