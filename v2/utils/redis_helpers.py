import redis
from config import settings

redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)

RATE_LIMIT = 2  # Number of messages per number
TIME_WINDOW = 60  # In seconds

def is_rate_limited(phone_number: str) -> bool:
    key = f"rate_limit:{phone_number}"
    current_count = redis_client.get(key)

    if current_count is None:
        redis_client.setex(key, TIME_WINDOW, 1)
        return False
    elif int(current_count) < RATE_LIMIT:
        redis_client.incr(key)
        return False
    else:
        return True