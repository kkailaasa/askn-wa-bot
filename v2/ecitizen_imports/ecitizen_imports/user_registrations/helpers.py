import logging
from django.contrib.auth.models import User
from .forms import UserRegistrationForm
from . import keycloak
from userprofiles.models import UserProfile
from .models import VerificationToken
from .emails import send_verification_email
from cities_light.models import Country
from zones.models import UserZone
from .verification import generate_verification_token
import phonenumbers

logger = logging.getLogger(__name__)

def populate_user(phone_number: str, email: str, first_name: str, last_name: str) -> User:
    username = None
    if email:
        username = email
    else:
        email = f"{phone_number}@ecitizen.info"
        username = phone_number
    logger.info("Username = " + username)
    user, created = User.objects.update_or_create(username = username,
                                              defaults={'email': email,
                                                        'first_name': first_name,
                                                        'last_name': last_name,
                                                        'phone_number': phone_number,
                                                        'phone_number_verified': True
                                                        })
    print("Created: " + str(created))    
    return user

def create_send_verification_token(request, user):
    token = generate_verification_token()
    print("====Token=======")
    print(token)    
    # Store token in the database
    VerificationToken.objects.create(user=user, token=token)    
    # Send verification link or notification to the user
    send_verification_email(request, user, token)
    
def register_user(request):
    # Process user registration form data
    username: str = request.data['email']
    password: str = request.data['password']
    email: str = request.data['email']
    first_name: str = request.data['first_name']
    last_name: str = request.data['last_name']
    country: str = request.data['country_code']
    zone: str = request.data['zone_code']
    gender: str = request.data['gender']

    # When data is from Django form, the value is phonenumbers.PhoneNumber
    if isinstance(request.data["phone_number"], phonenumbers.PhoneNumber):
        ph_num = request.data['phone_number']
    else:
        # Data from DRF the phone value is a simple string
        ph_num = phonenumbers.parse(request.data["phone_number"], None)

    phone_number: str = phonenumbers.format_number(ph_num, phonenumbers.PhoneNumberFormat.E164)
    
    user_data = {
        'username': username,
        "credentials": [{"value": password,"type": "password",}],
        'email': email,
        'firstName': first_name,
        'lastName': last_name,
        'requiredActions': ['VERIFY_EMAIL'],
        'enabled': True,
        'attributes': {
            'country': country,
            'zone': zone,
            'gender': gender, 
            'phone': phone_number
        }
    }
    
    print(username)
    print(gender)
    print(zone)
    print(phone_number)
    print(country)
    
    users = keycloak.get_user(email)
    logger.info("register_user - response from keycloak: " + str(users))
    if len(users) <= 0:
        keycloak.register_user_with_keycloak(user_data)
        user = populate_user(phone_number, email, first_name, last_name)
        return user
    elif users[0]['emailVerified']:
        return "already verified"
    elif not users[0]['emailVerified']:
        vt = VerificationToken.objects.filter(user__email = email).first()
        if vt is None:
            logger.info("register_user: Verification Token not found: " + email)
            user = User.objects.filter(email=email).first()
            if user is None:
                user = populate_user(phone_number, email, first_name, last_name)
                user = User.objects.filter(email=email).first()
            create_send_verification_token(request, user)
            return "email sent"
        elif vt and not vt.verified:
            user = User.objects.filter(email=email).first()
            send_verification_email(request, user, vt.token)
            return "email sent"
        elif vt and vt.verified:
            vt.verified = False
            vt.save()
            send_verification_email(request, user, vt.token)
            return "email sent"
        else:
            logger.error("register_user: Error state")
            pass
    else:
        pass
    return None

def enable_user(email: str, epassport_number: str):
    keycloak.enable(email, epassport_number)
    
def get_attribute(name, attributes):
    if name in attributes:
        return attributes[name][0]
    else:
        return None
    
def populate_user_profile(users):
    print(users)
    print(len(users))
    if len(users) == 1:
        keycloak_user = users[0]
        email = keycloak_user['email']
        firstName = keycloak_user['firstName']
        lastName = keycloak_user['lastName']
        if 'attributes' not in keycloak_user:
            keycloak_user['attributes'] = {}
        k_attributes = keycloak_user['attributes']
        country = get_attribute('country', k_attributes)
        zone = get_attribute('zone', k_attributes)
        phone_number_verified = get_attribute('phoneNumberVerified', k_attributes)
        gender = get_attribute('gender', k_attributes)
        if (phone_number_verified):
            phone_number = get_attribute('phoneNumber', k_attributes)
        else:
            phone_number = get_attribute('phone', k_attributes)
        if country:
            country = Country.objects.filter(code2 = country).first()
        if zone:
            zone = UserZone.objects.filter(slug = zone).first()
        user_profile = UserProfile.objects.filter(email=email).first()
        
        if not user_profile.first_name and firstName:
            user_profile.first_name = firstName

        if not user_profile.last_name and lastName:
            user_profile.last_name = lastName

        if not user_profile.phone_number and phone_number:
            user_profile.phone_number = phone_number

        print("====gender: " + user_profile.gender)
        print(gender)
        if not user_profile.gender and gender:
            user_profile.gender = gender

        if not user_profile.zone and zone:
            user_profile.zone = zone

        if not user_profile.country and country:
            user_profile.country = country

        user_profile.save()
    print("===========end populating user profile=============")    

def populate_user_profile_by_email(email: str):
    users = keycloak.get_user(email)
    print("Populating user profile=============: " + email)
    populate_user_profile(users)

def populate_user_profile_by_phone_number(phone_number: str):
    users = keycloak.get_user_by_phone(phone_number)
    print("Populating user profile phone =============: " + phone_number)
    populate_user_profile(users)
    return users

def get_user_from_keycloak_by_phone_number(phone_number: str):
    users = keycloak.get_user_by_phone(phone_number)
    return users
