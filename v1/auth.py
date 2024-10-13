from keycloak_utils import get_user_by_phone
import redis

redis_client = redis.StrictRedis(host='redis', port=6379)
# 7 days
AUTH_TIME_WINDOW = 7 * 24 * 60 * 60

def is_user_authorized(phone_number):
    phone_number = phone_number.split(':')[1].strip()
    key = f"auth_phone:{phone_number}"
    auth_user = redis_client.get(key)

    if auth_user is None:
        users = get_user_by_phone(phone_number)
        if len(users) == 1:
            redis_client.setex(key, AUTH_TIME_WINDOW, 1)
            return True
        return False
    return True
