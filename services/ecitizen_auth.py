from keycloak import KeycloakAdmin, KeycloakOpenIDConnection
from keycloak.exceptions import KeycloakError
from core.config import settings
from utils.redis_pool import get_redis_client
from functools import lru_cache
import json
import logging
import secrets
import time
import redis
from typing import Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client = get_redis_client()

class KeycloakOperationError(Exception):
    """Custom exception for Keycloak operations."""
    pass

@lru_cache(maxsize=1)
def get_keycloak_admin():
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

def create_keycloak_admin():
    return get_keycloak_admin()
    
    except KeycloakError as e:
        logger.error(f"Failed to create Keycloak admin: {str(e)}")
        raise KeycloakOperationError("Failed to initialize Keycloak admin")

def get_cache_key(identifier: str, identifier_type: str) -> str:
    return f"keycloak_user:{identifier_type}:{identifier}"

def get_from_cache(key: str) -> Optional[Dict[str, Any]]:
    try:
        cached_data = redis_client.get(key)
        if cached_data:
            return json.loads(cached_data)
    except redis.RedisError as e:
        logger.error(f"Redis error while getting data from cache: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error while getting data from cache: {str(e)}")
    return None

def set_in_cache(key: str, data: Dict[str, Any]):
    try:
        redis_client.setex(key, settings.KEYCLOAK_CACHE_EXPIRATION, json.dumps(data))
    except (redis.RedisError, json.JSONDecodeError) as e:
        logger.error(f"Error setting data in cache: {str(e)}")

def get_user_info(user: Dict[str, Any]) -> Dict[str, Any]:
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

def get_user_by_identifier(identifier: str, identifier_type: str) -> Optional[Dict[str, Any]]:
    cache_key = get_cache_key(identifier, identifier_type)
    cached_user = get_from_cache(cache_key)

    if cached_user:
        logger.info(f"User data for {identifier_type} {identifier} retrieved from cache")
        return cached_user

    try:
        keycloak_admin = create_keycloak_admin()
        if identifier_type == "email":
            users = keycloak_admin.get_users({"email": identifier})
        elif identifier_type == "phone":
            users = keycloak_admin.get_users({"q": f"phoneNumber:{identifier}"})
        else:
            raise ValueError(f"Invalid identifier_type: {identifier_type}")

        if len(users) == 1:
            user_info = get_user_info(users[0])
            set_in_cache(cache_key, user_info)
            logger.info(f"User data for {identifier_type} {identifier} retrieved from Keycloak and cached")
            return user_info
        
        logger.info(f"User with {identifier_type} {identifier} not found")
        return None
    except KeycloakError as e:
        logger.error(f"Keycloak error while getting user by {identifier_type}: {str(e)}")
        raise KeycloakOperationError(f"Failed to get user by {identifier_type}")

def get_users_by_email(email: str) -> List[Dict[str, Any]]:
    try:
        keycloak_admin = create_keycloak_admin()
        users = keycloak_admin.get_users({"email": email})
        return [get_user_info(user) for user in users]
    except KeycloakError as e:
        logger.error(f"Keycloak error while getting users by email: {str(e)}")
        raise KeycloakOperationError("Failed to get users by email")

def get_user_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    return get_user_by_identifier(phone_number, "phone")

def get_user_by_phone_or_username(identifier: str) -> Optional[Dict[str, Any]]:
    try:
        keycloak_admin = create_keycloak_admin()
        # Check username
        users = keycloak_admin.get_users({"username": identifier})
        if not users:
            # Check phoneNumber attribute
            users = keycloak_admin.get_users({"q": f"phoneNumber:{identifier}"})
        
        if users:
            return get_user_info(users[0])
        return None
    except KeycloakError as e:
        logger.error(f"Keycloak error while getting user: {str(e)}")
        raise KeycloakOperationError("Failed to get user")

def create_user_with_phone(phone_number: str, first_name: str, last_name: str, gender: str, country: str) -> Dict[str, Any]:
    try:
        keycloak_admin = create_keycloak_admin()

        user_data = {
            "username": phone_number,
            "enabled": True,
            "firstName": first_name,
            "lastName": last_name,
            "attributes": {
                "phoneNumber": [phone_number],
                "phoneType": ["whatsapp"],
                "gender": [gender],
                "country": [country]
            }
        }

        user_id = keycloak_admin.create_user(user_data)
        logger.info(f"User created with phone number: {phone_number}")
        return {"user_id": user_id, "message": "User created successfully."}
    except KeycloakError as e:
        logger.error(f"Keycloak error while creating user: {str(e)}")
        raise KeycloakOperationError("Failed to create user")

def add_phone_to_user(user_id: str, phone_number: str) -> Dict[str, Any]:
    try:
        keycloak_admin = create_keycloak_admin()
        user_info = keycloak_admin.get_user(user_id)
        attributes = user_info.get('attributes', {})
        attributes['phoneNumber'] = [phone_number]
        keycloak_admin.update_user(user_id=user_id, payload={"attributes": attributes})
        logger.info(f"Phone number added for user ID: {user_id}")
        return {"message": "Phone number added successfully."}
    except KeycloakError as e:
        logger.error(f"Keycloak error while adding phone to user: {str(e)}")
        raise KeycloakOperationError("Failed to add phone to user")

def check_email_exists(email: str) -> bool:
    try:
        keycloak_admin = create_keycloak_admin()
        users_by_username = keycloak_admin.get_users({"username": email})
        users_by_email = keycloak_admin.get_users({"email": email})
        return bool(users_by_username or users_by_email)
    except KeycloakError as e:
        logger.error(f"Keycloak error while checking email existence: {str(e)}")
        raise KeycloakOperationError("Failed to check email existence")

def add_email_to_user(user_id: str, email: str) -> Dict[str, Any]:
    try:
        keycloak_admin = create_keycloak_admin()
        keycloak_admin.update_user(user_id=user_id, payload={"email": email})
        logger.info(f"Email added for user ID: {user_id}")
        return {"message": "Email added successfully."}
    except KeycloakError as e:
        logger.error(f"Keycloak error while adding email to user: {str(e)}")
        raise KeycloakOperationError("Failed to add email to user")

def verify_email(email: str) -> Dict[str, Any]:
    try:
        keycloak_admin = create_keycloak_admin()
        users = keycloak_admin.get_users({"email": email})
        if not users:
            raise KeycloakOperationError("User not found")
        user_id = users[0]['id']
        keycloak_admin.update_user(user_id=user_id, payload={"emailVerified": True})
        logger.info(f"Email verified for user with email: {email}")
        return {"message": "Email verified successfully."}
    except KeycloakError as e:
        logger.error(f"Keycloak error while verifying email: {str(e)}")
        raise KeycloakOperationError("Failed to verify email")

def generate_otp() -> str:
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])  # Generate a 6-digit numeric OTP

def store_otp(email: str, otp: str):
    try:
        redis_client.setex(f"otp:{email}", 600, otp)  # OTP valid for 10 minutes
    except redis.RedisError as e:
        logger.error(f"Redis error while storing OTP: {str(e)}")
        raise

def verify_otp(email: str, otp: str) -> Dict[str, Any]:
    try:
        stored_otp = redis_client.get(f"otp:{email}")
        if not stored_otp:
            return {"valid": False, "message": "OTP expired or not found"}

        if stored_otp.decode() == otp:
            redis_client.delete(f"otp:{email}")
            return {"valid": True, "message": "OTP verified successfully"}

        return {"valid": False, "message": "Invalid OTP"}
    except redis.RedisError as e:
        logger.error(f"Redis error while verifying OTP: {str(e)}")
        raise

class RateLimiter:
    def __init__(self):
        self.redis_client = get_redis_client()

    def is_rate_limited(self, key: str, limit: int, period: int) -> bool:
        current = int(time.time())
        key = f"rate_limit:{key}"
        
        with self.redis_client.pipeline() as pipe:
            pipe.zremrangebyscore(key, 0, current - period)
            pipe.zcard(key)
            pipe.zadd(key, {current: current})
            pipe.expire(key, period)
            _, count, _, _ = pipe.execute()
        
        return count > limit

def store_temp_data(key: str, data: Dict[str, Any], expiry: int = 3600):
    redis_key = f"temp_data:{key}"
    redis_client.setex(redis_key, expiry, json.dumps(data))

def get_temp_data(key: str) -> Optional[Dict[str, Any]]:
    redis_key = f"temp_data:{key}"
    data = redis_client.get(redis_key)
    if data:
        return json.loads(data)
    return None

def delete_temp_data(key: str):
    redis_key = f"temp_data:{key}"
    redis_client.delete(redis_key)

rate_limiter = RateLimiter()

__all__ = [
    'KeycloakOperationError',
    'create_keycloak_admin',
    'get_user_by_email',
    'get_user_by_phone',
    'get_user_by_phone_or_username',
    'create_user_with_phone',
    'add_phone_to_user',
    'check_email_exists',
    'add_email_to_user',
    'verify_email',
    'generate_otp',
    'store_otp',
    'verify_otp',
    'store_temp_data',
    'get_temp_data',
    'delete_temp_data',
    'rate_limiter',
    'RateLimiter',
]