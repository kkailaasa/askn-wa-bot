from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import View
from urllib.parse import urlencode

from .models import UserProfile, EPassportNumber
from .forms import UserProfileForm
from .helpers import create_epassport_number, create_epassport_number


class UserProfileUpsertView(LoginRequiredMixin, View):
    login_url = "/"
    redirect_field_name = "next"
    form_class = UserProfileForm
    template_name = 'profile.html' # upsert.html
    #success_url = "/"
    
    def __create_or_get_user_profile(self, user) -> UserProfile:
        user_profile: UserProfile = None
         
        try:
            user_profile = UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            user_profile = UserProfile.objects.create(user=user, email=user.email,)
        return user_profile
    
    def get(self, request, *args, **kwargs):
        user = request.user
        redirect_to = request.GET.get(self.redirect_field_name)
        user_profile = self.__create_or_get_user_profile(user)
        
        epassport: EPassportNumber = None
        try:        
            epassport = EPassportNumber.objects.get(user_profile=user_profile)
        except EPassportNumber.DoesNotExist:
            epassport = create_epassport_number(user_profile=user_profile)
        
        print(user_profile)    
        profile_form = UserProfileForm(instance=user_profile)
        
        context = {
            'user': user,
            'next': redirect_to,
            'profile_form': profile_form,
            'epassport': epassport,
        }
        return render(request, self.template_name, context=context)
    
    def post(self, request, *args, **kwargs):
        print("-----POST-------- userprofile")
        user = request.user
        user_profile = self.__create_or_get_user_profile(user)        
        next_url = request.GET.get(self.redirect_field_name)
        if not next_url:
            next_url = request.POST.get(self.redirect_field_name)
        redirect_to = None
        if next_url:
            redirect_to = next_url
        else:
            redirect_to = "/me"        
        profile_form = UserProfileForm(request.POST, instance=user_profile)         
        print(user_profile)
        print("-------------- before valid: " + profile_form.is_valid().__str__())    
        if profile_form.is_valid():
            print("profile_form is valid")
            profile_form.save()
            user_profile = UserProfile.objects.get(user=user)
            create_epassport_number(user_profile)        
            print(redirect_to)
            return redirect(redirect_to)
        else:
            print("profile_form is not valid")
            print(profile_form.errors)
            epassport: EPassportNumber = None
            try:        
                epassport = EPassportNumber.objects.get(user_profile=user_profile)
            except EPassportNumber.DoesNotExist:
                epassport = create_epassport_number(user_profile=user_profile)
            context = {
                'user': user,
                'next': redirect_to,
                'profile_form': profile_form,
                'epassport': epassport,
            }
            return render(request, self.template_name, context=context)