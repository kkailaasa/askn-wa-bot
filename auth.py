from keycloak_utils import get_user_by_phone


def is_user_authorized(phone_number):
    phone_number = phone_number.split(':')[1].strip()
    users = get_user_by_phone(phone_number)
    if len(users) == 1:
        return True
    return False
    
