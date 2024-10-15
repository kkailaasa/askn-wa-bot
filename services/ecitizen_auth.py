from keycloak import KeycloakAdmin, KeycloakOpenIDConnection
from core.config import settings
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

def get_cache_key(identifier: str, identifier_type: str) -> str:
    return f"keycloak_user:{identifier_type}:{identifier}"

def get_from_cache(key: str) -> dict:
    cached_data = redis_client.get(key)
    if cached_data:
        return json.loads(cached_data)
    return None

def set_in_cache(key: str, data: dict):
    redis_client.setex(key, settings.KEYCLOAK_CACHE_EXPIRATION, json.dumps(data))

def get_user_info(user: dict) -> dict:
    attributes = user.get('attributes', {})
    return {
        "email": user.get('email', ''),
        "enabled": user.get('enabled', False),
        "phoneType": attributes.get('phoneType', [None])[0],
        "phoneNumber": attributes.get('phoneNumber', [None])[0],
        "gender": attributes.get('gender', [None])[0],
        "phoneNumberVerified": attributes.get('phoneNumberVerified', [None])[0],
        "firstName": user.get('firstName', ''),
        "lastName": user.get('lastName', '')
    }

def get_user_by_email(email: str) -> dict:
    cache_key = get_cache_key(email, "email")
    cached_user = get_from_cache(cache_key)

    if cached_user:
        logger.info(f"User data for email {email} retrieved from cache")
        return cached_user

    keycloak_admin = create_keycloak_admin()
    users = keycloak_admin.get_users({"email": email})

    if len(users) == 1:
        user_info = get_user_info(users[0])
        set_in_cache(cache_key, user_info)
        logger.info(f"User data for email {email} retrieved from Keycloak and cached")
        return user_info

    logger.info(f"User with email {email} not found")
    return None

def get_user_by_phone(phone_number: str) -> dict:
    cache_key = get_cache_key(phone_number, "phone")
    cached_user = get_from_cache(cache_key)

    if cached_user:
        logger.info(f"User data for phone {phone_number} retrieved from cache")
        return cached_user

    keycloak_admin = create_keycloak_admin()
    users = keycloak_admin.get_users({"q": f"phoneNumber:{phone_number}"})

    if len(users) == 1:
        user_info = get_user_info(users[0])
        set_in_cache(cache_key, user_info)
        logger.info(f"User data for phone {phone_number} retrieved from Keycloak and cached")
        return user_info

    logger.info(f"User with phone {phone_number} not found")
    return None