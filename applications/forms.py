from django.forms import ModelForm
from django import forms
from django.contrib.auth import get_user_model
from datetime import date, datetime
from . import models as Essco_Models
from django_flatpickr.widgets import DatePickerInput

from phonenumber_field.formfields import PhoneNumberField
from phonenumber_field.phonenumber import PhoneNumber

User = get_user_model()

class RatesForm(ModelForm):
    class Meta:
        model = Essco_Models.InterestRate
        exclude = ('created_by','updated_by')



class ApplicationForm(ModelForm):
    accept_terms = forms.BooleanField(
        required=True,
        error_messages={"required": "You must accept the terms to continue."}
    )

    Cell_Phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={
            'type': 'text',  # ⭐ Override type="tel"
            'placeholder': '246-564-5676',
            'class': 'form-control',
            'id': 'id_Cell_Phone'
        })
    )
    Home_Phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={
            'type': 'text',  # ⭐ Override type="tel"
            'placeholder': '246-564-5676',
            'class': 'form-control',
            'id': 'id_Cell_Phone'
        })
    )
    Work_Phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={
            'type': 'text',  # ⭐ Override type="tel"
            'placeholder': '246-564-5676',
            'class': 'form-control',
            'id': 'id_Cell_Phone'
        })
    )
    Employer_Num = forms.CharField(max_length=20, widget=forms.TextInput(attrs={
            'type': 'text',  # ⭐ Override type="tel"
            'placeholder': '246-564-5676',
            'class': 'form-control',
            'id': 'id_Cell_Phone'
        })
    )
    Reference1_Contact_Number = forms.CharField(max_length=20, widget=forms.TextInput(attrs={
            'type': 'text',  # ⭐ Override type="tel"
            'placeholder': '246-564-5676',
            'class': 'form-control',
            'id': 'id_Cell_Phone'
        })
    )
    Reference2_Contact_Number = forms.CharField(max_length=20, widget=forms.TextInput(attrs={
            'type': 'text',  # ⭐ Override type="tel"
            'placeholder': '246-564-5676',
            'class': 'form-control',
            'id': 'id_Cell_Phone'
        })
    )

    class Meta:
        model = Essco_Models.ApplicationModel
        exclude = ('Total_Monthly_living_expenses','Total_Monthly_debt','Monthly_Obligations','Disposable_Income','Debt_To_Income_Ratio','Living_Expense_Ratio',
        'Total_Debt_Service_Ratio','Approval_Status','Total_Credit_Allowed','Deposit','Financed_Amt','Six','Twelve','Eighteen','Twenty_Four','Thirty','Thirty_Six',
        'created_by','updated_by','Disposable_Income_After','RR','PAYE','NIS','Gross_Monthly_Income_AT','deposit_paid','deposit_paid_date','deposit_payment_method',
        'deposit_receipt_number','deposit_status','deposit_payment','version')
        widgets = {
            'DOB': DatePickerInput(),
        }

    def clean(self):
        cleaned_data = super().clean()
        less_than_six = cleaned_data.get("less_than_six")
        len_employ = cleaned_data.get("Len_Employ")

        if less_than_six == "No" and len_employ == "Less than 6 months":
            raise forms.ValidationError("Invalid employment selection")
        return cleaned_data

    def clean_DOB(self):
        dob = self.cleaned_data.get('DOB')

        if not dob:
            raise forms.ValidationError("Date of Birth is required.")

        # If dob is a string, convert it to date
        if isinstance(dob, str):
            try:
                dob = datetime.strptime(dob, '%Y-%m-%d').date()
            except ValueError:
                raise forms.ValidationError("Invalid date format. Please use YYYY-MM-DD.")

        # ✅ Use date.today() - date is imported at the top
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        if age < 18:
            raise forms.ValidationError("You must be at least 18 years old to apply.")

        if age > 100:
            raise forms.ValidationError("Please check your date of birth.")

        return dob




class AdminApplicationForm(forms.ModelForm):
    class Meta:
        model = Essco_Models.ApplicationModel
        exclude = ('Total_Monthly_living_expenses','Total_Monthly_debt','Monthly_Obligations','Disposable_Income','Debt_To_Income_Ratio','Living_Expense_Ratio',
        'Total_Debt_Service_Ratio','Approval_Status','Total_Credit_Allowed','Deposit','Financed_Amt','Six','Twelve','Eighteen','Twenty_Four','Thirty','Thirty_Six',
        'created_by','updated_by','Disposable_Income_After','RR','PAYE','NIS','Gross_Monthly_Income_AT','item_sku','item_name','deposit_paid','deposit_paid_date',
        'deposit_payment_method','deposit_receipt_number','deposit_status','deposit_payment')
        widgets = {
        'DOB': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #Make customer field read-only if it has a value
        if self.instance and self.instance.customer:
                self.fields['customer'].widget.attrs['readonly'] = True
                self.fields['customer'].disabled = True
    def clean(self):
        cleaned_data = super().clean()

        less_than_six = cleaned_data.get("less_than_six")
        len_employ = cleaned_data.get("Len_Employ")

        if less_than_six == "No" and len_employ == "Less than 6 months":
            raise forms.ValidationError(
                "Invalid employment selection"
            )

        return cleaned_data