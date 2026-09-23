from django import forms

from dojos.models import Dojo

from .models import DojoApplication, MentorApplication


class BackgroundCheckUploadForm(forms.Form):
    # A plain Form, not a ModelForm: the upload view resolves a token to
    # either a DojoApplication or a MentorApplication, so this needs to
    # work against whichever one it finds rather than being tied to one.
    document = forms.FileField(
        label="Uittreksel uit het strafregister (model 2)",
        widget=forms.ClearableFileInput(attrs={"class": "cd-form__input body"}),
    )


class DojoApplicationForm(forms.ModelForm):
    class Meta:
        model = DojoApplication
        fields = [
            "applicant_name", "applicant_email", "applicant_phone",
            "area", "preferred_schedule", "proposed_venue",
            "message", "consent", "background_check_consent",
        ]
        widgets = {
            "applicant_name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Jane Doe"}),
            "applicant_email": forms.EmailInput(attrs={"class": "cd-form__input body", "placeholder": "jane.doe@example.com"}),
            "applicant_phone": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "+32 4xx xx xx xx"}),
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
        # BooleanField defaults to required=False on a ModelForm regardless
        # of the model field's own blank= setting (an unchecked box is a
        # valid "False") — these actually have to be ticked to submit.
        self.fields["consent"].required = True
        self.fields["background_check_consent"].required = True


class MentorApplicationForm(forms.ModelForm):
    class Meta:
        model = MentorApplication
        fields = ["applicant_name", "applicant_email", "applicant_phone", "dojo", "role", "about", "background_check_consent"]
        widgets = {
            "applicant_name": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "Tom Verstraete"}),
            "applicant_email": forms.EmailInput(attrs={"class": "cd-form__input body", "placeholder": "tom@example.com"}),
            "applicant_phone": forms.TextInput(attrs={"class": "cd-form__input body", "placeholder": "+32 4xx xx xx xx"}),
            "dojo": forms.Select(attrs={"class": "cd-form__select body"}),
            "role": forms.Select(attrs={"class": "cd-form__select body"}),
            "about": forms.Textarea(attrs={
                "class": "cd-form__input body", "rows": 4,
                "placeholder": "e.g. Python, Scratch, web, robotics, event-day support — no experience necessary.",
            }),
            "background_check_consent": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dojo"].queryset = Dojo.objects.order_by("name")
        self.fields["dojo"].empty_label = "Not sure yet — any dojo"
        self.fields["background_check_consent"].required = True
