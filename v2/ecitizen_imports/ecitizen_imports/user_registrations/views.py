from django.shortcuts import render
from django.views import View
from django.contrib.auth.models import User

from .forms import UserRegistrationForm
from .models import VerificationToken
from . import helpers
from .verification import generate_verification_token
from .emails import send_verification_email
from userprofiles.helpers import create_epassport_number, create_or_get_user_profile
from userprofiles.models import EPassportNumber, UserProfile


class UserRegistrationView(View):

    def parse_user_form_data(self, registration_form: UserRegistrationForm) -> dict:
        registration_req = {
            "username": registration_form.cleaned_data["email"],
            "password": registration_form.cleaned_data["password"],
            "email": registration_form["email"].value(),
            "first_name": registration_form.cleaned_data["first_name"],
            "last_name": registration_form.cleaned_data["last_name"],
            "country_code": registration_form.cleaned_data["country"].code2,
            "zone_code": registration_form.cleaned_data["zone"].slug,
            "gender": registration_form.cleaned_data["gender"],
            "phone_number": registration_form.cleaned_data["phone_number"],
        }
        return registration_req
    def get(self, request):
        form = UserRegistrationForm()
        return render(request, 'user_registration_form.html', {'form': form})

    def post(self, request):
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            print("----------in POST----------")
            # Process the form data and invoke the REST API for registration
            # You can access the form fields using form.cleaned_data dictionary
            # Invoke the REST API here
            # ...
            self.data = self.parse_user_form_data(form)
            request.data = self.data
            user = helpers.register_user(request)
            if user and type(user) == str and user == "already verified":
                return render(request, "user_already_verified.html")
            #elif user and type(user) == str and user == "email sent":                
            elif user and type(user) == User:
                helpers.create_send_verification_token(request, user)
            else:
                pass

            return render(request, 'user_registration_success.html')
        else:
            return render(request, 'user_registration_form.html', {'form': form})


def verify_token(request, token: str):
    print(token)
    # Retrieve the verification token from the database
    try:
        verification_token = VerificationToken.objects.get(token=token)
        if not verification_token.verified:
            # raise Http404("Invalid token or expired")    
            email = verification_token.user.email
            # Mark the token as verified
            verification_token.verified = True
            verification_token.save()
            
            user_profile = create_or_get_user_profile(verification_token.user)
            epassport_number: EPassportNumber = create_epassport_number(user_profile)
            helpers.enable_user(email, epassport_number.epassport_number)
            
            try:
                helpers.populate_user_profile_by_email(email)
            except Exception as ex:
                print("=========================")
                print(str(ex))
                print("Error populating user profile: " + email)
                pass
                
        # Render a success page or perform any other actions
        return render(request, 'verification_success.html')
    except VerificationToken.DoesNotExist:
        return render(request, 'verification_failure.html')
