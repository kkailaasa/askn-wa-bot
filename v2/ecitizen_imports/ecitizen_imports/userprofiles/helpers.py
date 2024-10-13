import secrets
import string
import random

from .models import UserProfile, EPassportNumber


def __generate_random_passport_number() -> int:
    # Generate a random combination of letters and numbers
    # letters = random.choices(string.ascii_uppercase, k=2)
    random_number = secrets.randbelow(900000000) + 100000000

    # Combine the letters and numbers to form the passport number
    # passport_number = ''.join(letters + numbers)

    return random_number


def __generate_passport_number(acc=0) -> int:
    number = __generate_random_passport_number()
    if len(str(number)) != 9:
        print("Invalid. length != 9: " + str(number))
        return __generate_passport_number(acc + 1)

    random_alphabet = random.choice(string.ascii_uppercase)
    if EPassportNumber.objects.filter(number=number, alphabet=random_alphabet).exists():
        return __generate_passport_number(acc + 1)
    else:
        print("Number of attempts to get unique passport number: " + str(acc))
        return random_alphabet, number


def __create_epassport_number(
    alphabet: str, number: int, user_profile: UserProfile
) -> EPassportNumber:
    epassport_number: str = f"{alphabet}{number}"
    return EPassportNumber.objects.create(
        epassport_number=epassport_number,
        alphabet=alphabet,
        number=number,
        user_profile=user_profile,
    )


def create_epassport_number(user_profile: UserProfile) -> EPassportNumber:
    epassport_number = None
    try:
        epassport_number = EPassportNumber.objects.get(user_profile=user_profile)
        print(f"EPassport Exists for {user_profile} {epassport_number}")
    except EPassportNumber.DoesNotExist:
        alphabet, number = __generate_passport_number()
        epassport_number = __create_epassport_number(alphabet, number, user_profile)
        print(f"EPassport Number Created: {alphabet}{number}")
    return epassport_number


def create_or_get_user_profile(user) -> UserProfile:
    user_profile: UserProfile = None

    try:
        user_profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        user_profile = UserProfile.objects.create(
            user=user,
            email=user.email,
        )
    return user_profile
