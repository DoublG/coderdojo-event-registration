from django import forms


class LoginForm(forms.Form):
    email = forms.CharField(
        label="Email",
        widget=forms.TextInput(attrs={
            "class": "cd-form__input body",
            "placeholder": "you@example.com",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "cd-form__input body"}),
    )
