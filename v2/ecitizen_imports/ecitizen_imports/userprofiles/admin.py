from django.contrib import admin

from django import forms
from dal import autocomplete

from simple_history.admin import SimpleHistoryAdmin

# Register your models here.
from .models import UserProfile, UserProfilePhoto, EPassportNumber

class EPassportNumberAdmin(SimpleHistoryAdmin,admin.ModelAdmin):
    list_display = [field.name for field in EPassportNumber._meta.fields]
    search_fields = [field.name for field in EPassportNumber._meta.fields]
    list_filter = [field.name for field in EPassportNumber._meta.fields]
        
admin.site.register(EPassportNumber, EPassportNumberAdmin)


class UserProfileAdminForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = '__all__'
        widgets = {
            'country': autocomplete.ModelSelect2(url='select2_fk_country'),
            'state': autocomplete.ModelSelect2(url='select2_fk_region'),
            'city': autocomplete.ModelSelect2(url='select2_fk_city'),
            'user': autocomplete.ModelSelect2(url='select2_fk_user'),
        }
    
class UserProfileAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    form = UserProfileAdminForm
    list_display = [
                     'id',
                     'first_name',
                     'last_name',
                     'spiritual_name',
                     'date_of_birth',
                     'gender',
                     'email',
                     'phone_number',
                     'country',
                     'state',
                     'city',
                     'address_1',
                     'postal_code',
                     'zone',
                     'created_at',
                     'updated_at'
                    ]
    
    search_fields = ['first_name',
                     'last_name',
                     'spiritual_name',
                     'date_of_birth',
                     'gender',
                     'email',
                     'phone_number',
                     'country__name',
                     'state__name',
                     'city__name',
                     'address_1',
                     'postal_code',
                     'zone__slug',
                     'zone__name'
                     ]
    
admin.site.register(UserProfile, UserProfileAdmin)

class UserProfileAdminForm(forms.ModelForm):
    class Meta:
        model = UserProfilePhoto
        fields = '__all__'
        widgets = {
            'user_profile': autocomplete.ModelSelect2(url='select2_fk_userprofile'),
            'created_by': autocomplete.ModelSelect2(url='select2_fk_user'),
            'updated_by': autocomplete.ModelSelect2(url='select2_fk_user'),
        }

@admin.register(UserProfilePhoto)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileAdminForm    