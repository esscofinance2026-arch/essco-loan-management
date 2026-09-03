from django.forms import ModelForm
from django import forms
from datetime import date
from . import models as Essco_Models
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm as DjangoSetPasswordForm

User = get_user_model()

class MaintenanceSettingsForm(forms.ModelForm):
    """Form for maintenance mode settings"""
    class Meta:
        model = Essco_Models.SiteSettings
        fields = ['maintenance_mode']
        widgets = {
            'maintenance_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'maintenance_mode': 'Enable Maintenance Mode',
        }

class EmailRegistrationForm(forms.Form):
    """Simple registration form - email only"""

    email = forms.EmailField(
        max_length=100,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autofocus': 'autofocus',
            'required': True,
        })
    )

    def clean_email(self):
        """Validate email format and check if it exists"""
        email = self.cleaned_data.get('email')

        # Basic email validation
        if not email:
            raise forms.ValidationError('Email address is required.')

        # You can add custom validation here if needed
        # For example, check if email is from allowed domains
        # allowed_domains = ['gmail.com', 'yahoo.com', 'hotmail.com']
        # domain = email.split('@')[1]
        # if domain not in allowed_domains:
        #     raise forms.ValidationError('Please use a valid email domain.')

        return email


class SetPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password',
            'required': True,
        }),
        strip=False,
    )
    new_password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password',
            'required': True,
        }),
        strip=False,
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_new_password2(self):
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')

        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("Passwords don't match.")

        return password2

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')

        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters.")

        if password.isdigit():
            raise forms.ValidationError("Password cannot be entirely numeric.")

        common_passwords = ['password', '12345678', 'qwerty', 'abc123', 'password123']
        if password.lower() in common_passwords:
            raise forms.ValidationError("Password is too common.")

        return password

    def save(self, commit=True):
        """
        Save the new password
        """
        self.user.set_password(self.cleaned_data['new_password1'])
        if commit:
            self.user.save()
        return self.user
# Future forms for other tiles
# class GeneralSettingsForm(forms.ModelForm):
#     class Meta:
#         model = Essco_Models.OtherModel  # Different model
#         fields = ['field1', 'field2']

# class EmailSettingsForm(forms.ModelForm):
#     class Meta:
#         model = Essco_Models.EmailConfig  # Different model
#         fields = ['smtp_host', 'smtp_port', 'from_email']