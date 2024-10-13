from django import forms
from .models import UserProfile
from zones.models import UserZone
from consents.forms import DateInput, PhoneInput

class UserProfileForm(forms.ModelForm):
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'class': 'form-control', 'readonly': 'readonly'}))
    zone = forms.ModelChoiceField(label='Zone', queryset=UserZone.objects.filter(is_global=False).all(), required=True)
    spiritual_name = forms.CharField(required=False)
    
    class Meta:
        model = UserProfile
        fields = [
                    'first_name',
                    'last_name',
                    'spiritual_name',
                    'date_of_birth', 
                    'phone_number',
                    'email',
                    'zone',
                    'gender',
                    'country',
                    'state',
                    'city'
        ]
        widgets = {
            'date_of_birth': DateInput(),
            'phone_number': PhoneInput(),
        }
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            #self.fields['spiritual_name'].required = False
            #self.fields['email'].widget.attrs['readonly'] = True