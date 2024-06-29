from keycloak import get_user_by_phone


def is_user_authorized(phone_number):
    users = get_user_by_phone(phone_number)
    if len(users) == 1:
        return True
    return False
    