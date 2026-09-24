from django import forms

from dojos.models import Dojo

from .models import Application


class BackgroundCheckUploadForm(forms.Form):
    document = forms.FileField(
        label="Uittreksel uit het strafregister (model 2)",
        widget=forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
    )


class _ApplicationForm(forms.ModelForm):
    """Shared by both application kinds. The applicant's name and email come
    from their account (applying requires being logged in); only the phone
    number is asked for here, and saved onto the account."""

    phone = forms.CharField(
        required=False, max_length=30,
        widget=forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "+32 4xx xx xx xx"}),
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
        widgets = {
            "area": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Leuven"}),
            "preferred_schedule": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "e.g. Saturday mornings"}),
            "proposed_venue": forms.TextInput(attrs={
                "class": "cd-form__input body",
                "placeholder": "e.g. Leuven Public Library, a school, a community centre",
            }),
            "message": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 4,
                "placeholder": "Any relevant experience, a connection at the venue, why this area needs a dojo — whatever's useful for us to know.",
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
        widgets = {
            "dojo": forms.Select(attrs={"class": "cd-form__select body"}),
            "mentor_role": forms.Select(attrs={"class": "cd-form__select body"}),
            "message": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 4,
                "placeholder": "e.g. Python, Scratch, web, robotics, event-day support — no experience necessary.",
            }),
            "background_check_consent": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dojo"].queryset = Dojo.objects.public().order_by("name")
        self.fields["dojo"].empty_label = "Not sure yet — any dojo"
        self.fields["mentor_role"].required = True
        self.fields["mentor_role"].choices = Application.MENTOR_ROLE_CHOICES
