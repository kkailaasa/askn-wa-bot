from keycloak import KeycloakAdmin, KeycloakOpenIDConnection
from config import settings
import redis

redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
AUTH_TIME_WINDOW = 7 * 24 * 60 * 60

def create_keycloak_admin() -> KeycloakAdmin:
    keycloak_connection = KeycloakOpenIDConnection(
        server_url=settings.KEYCLOAK_SERVER_URL,
        user_realm_name="master",
        client_id=settings.KEYCLOAK_API_CLIENT_ID,
        realm_name=settings.KEYCLOAK_REALM,
        username=settings.KEYCLOAK_USER_NAME,
        password=settings.KEYCLOAK_PASSWORD,
        verify=True
    )
    return KeycloakAdmin(connection=keycloak_connection)

# def is_user_authorized(phone_number: str) -> bool:
#     phone_number = phone_number.split(':')[1].strip()
#     key = f"auth_phone:{phone_number}"
#     auth_user = redis_client.get(key)

#     if auth_user is None:
#         keycloak_admin = create_keycloak_admin()
#         users = keycloak_admin.get_users({"q": f"phoneNumber:{phone_number}"})
#         if len(users) == 1:
#             redis_client.setex(key, AUTH_TIME_WINDOW, 1)
#             return True
#         return False
#     return True

def get_user_by_email(email: str) -> dict:
    keycloak_admin = create_keycloak_admin()
    users = keycloak_admin.get_users({"email": email})

    if len(users) == 1:
        user = users[0]
        attributes = user.get('attributes', {})
        return {
            "email": email,
            "enabled": user.get('enabled', False),
            "phoneType": attributes.get('phoneType', [None])[0],
            "phoneNumber": attributes.get('phoneNumber', [None])[0],
            "gender": attributes.get('gender', [None])[0],
            "phoneNumberVerified": attributes.get('phoneNumberVerified', [None])[0],
            "firstName": user.get('firstName', ''),
            "lastName": user.get('lastName', '')
        }
    return None

# Function to get user info by phone number
def get_user_by_phone(phone_number: str) -> dict:
    keycloak_admin = create_keycloak_admin()
    users = keycloak_admin.get_users({"q": f"phoneNumber:{phone_number}"})

    if len(users) == 1:
        user = users[0]
        attributes = user.get('attributes', {})
        return {
            "enabled": user.get('enabled', False),
            "phoneType": attributes.get('phoneType', [None])[0],
            "phoneNumber": attributes.get('phoneNumber', [None])[0],
            "gender": attributes.get('gender', [None])[0],
            "phoneNumberVerified": attributes.get('phoneNumberVerified', [None])[0],
            "firstName": user.get('firstName', ''),
            "lastName": user.get('lastName', '')
        }
    return None