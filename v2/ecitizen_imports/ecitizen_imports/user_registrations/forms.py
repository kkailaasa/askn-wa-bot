from django import forms
from cities_light.models import Country
from phonenumber_field.formfields import PhoneNumberField
from django.core.validators import MinLengthValidator

from zones.models import UserZone
from userprofiles.fields import GenderField

class GenderFormField(forms.ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs['choices'] = [('', 'Select Gender'),  # Empty value option
                            *GenderField.GENDER_CHOICES,]
        #kwargs['max_length'] = 1
        super().__init__(*args, **kwargs)

class UserRegistrationForm(forms.Form):

    first_name = forms.CharField(label='First Name', required=True)
    last_name = forms.CharField(label='Last Name', required=True)
    spiritual_name = forms.CharField(label='Spiritual Name', required=False)
    
    gender = GenderFormField(label="Gender", required=True)
    
    email = forms.EmailField(label='Email', required=True)
    
    password = forms.CharField(validators=[MinLengthValidator(8)], label='Password', 
                               widget=forms.PasswordInput, required=True)
    confirm_password = forms.CharField(validators=[MinLengthValidator(8)], label='Confirm Password', 
                                       widget=forms.PasswordInput, required=True)
    country = forms.ModelChoiceField(label='Country', queryset=Country.objects.all(), required=True)
    phone_number = forms.CharField(label='Phone Number', required=True,)
    #'Incorrect International Calling Code or Mobile Number!'
    phone_number.error_messages['invalid'] = 'Please ensure that you have selected the correct country code and entered a valid phone number.'
    zone = forms.ModelChoiceField(label='Zone', queryset=UserZone.objects.filter(is_global=False).all(), required=True)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if email and password and password == email:
            self.add_error('password', 'Password cannot be same as email')
            
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match')
        
        return cleaned_data
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_asterisk_to_labels()

    def add_asterisk_to_labels(self):
        for field_name, field in self.fields.items():
            field.label = f'{field.label} *' if field.required else field.label
