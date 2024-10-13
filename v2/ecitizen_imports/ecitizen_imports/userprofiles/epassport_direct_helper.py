import logging
from django.contrib.auth.models import User
from user_registrations import helpers as ur_helpers, keycloak
from .models import UserProfile, EPassportNumber
from . import helpers

logger = logging.getLogger(__name__)

def get_create_epassport_by_user_profile(user_profile) -> EPassportNumber:
    try:
        epassport = EPassportNumber.objects.get(user_profile=user_profile)
    except EPassportNumber.DoesNotExist:
        epassport = helpers.create_epassport_number(user_profile=user_profile)
    return epassport

def update_user_with_epassport_email(phone_number: str, email: str, epassport_number: str):
    keycloak.update_by_phone_number(phone_number, email, epassport_number)
    user_profile = UserProfile.objects.filter(phone_number=phone_number).first()
    user_profile.email = email
    user_profile.save()
    
    user = user_profile.user
    user.email = email
    user.save()
    
def get_epassport_by_phone_number(phone_number: str) -> EPassportNumber:
    try:
        email = None
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number.strip()
                    
        user_profile = UserProfile.objects.filter(phone_number=phone_number, 
                                                  phone_number_verified=True).first()
                
        if user_profile is None:
            kc_users = ur_helpers.get_user_from_keycloak_by_phone_number(phone_number)
            if len(kc_users) == 0:
                raise Exception("User not found")
            
            kc_user = kc_users[0]    
            print("======")
            print(kc_user)
            if "email" in kc_user:
                email = kc_user['email']
            first_name = kc_user['firstName']
            last_name = kc_user['lastName']
            if "gender" in kc_user['attributes']:
                gender = kc_user['attributes']['gender'][0]
                
            user = None
            if email:
                user = User.objects.filter(email=email).first()
            else:
                user = User.objects.filter(username=phone_number).first()
                
            if user is None:                    
                user = ur_helpers.populate_user(phone_number, email, first_name, last_name)
            
            user_profile = UserProfile.objects.filter(user=user).first()
            
            if user_profile is None:
                if email:
                    _email = email
                else:
                    _email = ''
                user_profile = UserProfile.objects.create(user = user, 
                                        email = _email, 
                                        gender = gender,
                                        phone_number = phone_number, 
                                        phone_number_verified = True,
                                        first_name = first_name, 
                                        last_name = last_name)
            else:
                user_profile.phone_number = phone_number
                user_profile.save()
        # Get or create e-Passport for existing profile
        epassport: EPassportNumber = get_create_epassport_by_user_profile(user_profile)
        return epassport

    except Exception as ex:
        logger.error("Error at get_epassport_by_phone_number", exc_info=ex)
        raise ex