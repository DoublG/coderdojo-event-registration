from django import forms
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _


class ConfirmUsernameForm(forms.Form):
    """The organisation confirms deleting an account by typing its username
    (privacy.views.manage_privacy_delete)."""

    confirm = forms.CharField(widget=forms.TextInput(attrs={"autocomplete": "off"}))

    def __init__(self, account, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        # Lazy, like every label: rendered in the language of the request that shows it.
        self.fields["confirm"].label = lazy(
            lambda: _("Type the username, %(username)s, to confirm") % {"username": account.get_username()}, str,
        )()

    def clean_confirm(self):
        if self.cleaned_data["confirm"].strip() != self.account.get_username():
            raise forms.ValidationError(_("Type the account's username to confirm."))
        return self.cleaned_data["confirm"]
