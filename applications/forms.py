from django import forms
from django.utils.translation import gettext_lazy as _

from dojos.models import Dojo

from .models import Application


class BackgroundCheckUploadForm(forms.Form):
    document = forms.FileField(label=_("Document"))


class _ApplicationForm(forms.ModelForm):
    """Shared by both application kinds. The applicant's name and email come
    from their account (applying requires being logged in); only the phone
    number is asked for here, and saved onto the account."""

    phone = forms.CharField(
        label=_("Phone"), required=False, max_length=30,
        widget=forms.TextInput(attrs={"placeholder": _("+32 4xx xx xx xx")}),
    )

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account
        self.fields["phone"].initial = account.phone
        # A ModelForm BooleanField is optional by default; these have to be ticked.
        for name in ("consent", "background_check_consent"):
            if name in self.fields:
                self.fields[name].required = True


class ChampionApplicationForm(_ApplicationForm):
    class Meta:
        model = Application
        fields = ["area", "preferred_schedule", "proposed_venue", "message", "consent", "background_check_consent"]
        labels = {
            "area": _("City or area"), "preferred_schedule": _("Preferred day & time"),
            "proposed_venue": _("Proposed venue"), "message": _("What made you want to start a dojo?"),
            "consent": _("I understand CoderDojo sessions are always free and run by volunteers."),
            "background_check_consent": _("I understand a Belgian criminal record extract (model 2, Artikel 596.2) will be required."),
        }
        # The model's help texts are notes for the admin (English only): not shown here.
        help_texts = {
            "proposed_venue": _("Not confirmed yet? That's fine — we can help you find one."),
            "area": "", "preferred_schedule": "", "message": "", "consent": "", "background_check_consent": "",
        }
        # The input classes come from core.forms.SiteBoundField.
        widgets = {
            "area": forms.TextInput(attrs={"placeholder": _("Leuven")}),
            "preferred_schedule": forms.TextInput(attrs={"placeholder": _("e.g. Saturday mornings")}),
            "proposed_venue": forms.TextInput(attrs={
                "placeholder": _("e.g. Leuven Public Library, a school, a community centre"),
            }),
            "message": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": _("Any relevant experience, a connection at the venue, why this area needs a dojo — whatever's useful for us to know."),
            }),
            "consent": forms.CheckboxInput(),
            "background_check_consent": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].required = True


class MentorApplicationForm(_ApplicationForm):
    class Meta:
        model = Application
        fields = ["dojo", "mentor_role", "message", "background_check_consent"]
        labels = {
            "dojo": _("Which dojo?"), "mentor_role": _("Role"), "message": _("What would you like to help with?"),
            "background_check_consent": _("I understand a Belgian criminal record extract (model 2, Artikel 596.2) will be required."),
        }
        # The model's help texts are notes for the admin (English only): not shown here.
        help_texts = {"dojo": "", "message": "", "background_check_consent": ""}
        # The input classes come from core.forms.SiteBoundField.
        widgets = {
            "message": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": _("e.g. Python, Scratch, web, robotics, event-day support — no experience necessary."),
            }),
            "background_check_consent": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dojo"].queryset = Dojo.objects.public().order_by("name")
        self.fields["dojo"].empty_label = _("Not sure yet — any dojo")
        self.fields["mentor_role"].required = True
        self.fields["mentor_role"].choices = Application.MENTOR_ROLE_CHOICES
