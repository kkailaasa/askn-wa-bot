# utils/redis_helpers.py
from utils.redis_pool import get_redis_client
from core.config import settings

redis_client = get_redis_client()

def is_rate_limited(phone_number: str) -> bool:
    """
    Check if a phone number has exceeded its rate limit

    Args:
        phone_number: The phone number to check

    Returns:
        bool: True if rate limited, False otherwise
    """
    key = f"rate_limit:{phone_number}"
    current_count = redis_client.get(key)

    if current_count is None:
        # First message in the window
        redis_client.setex(key, settings.MESSAGE_RATE_WINDOW, 1)
        return False
    elif int(current_count) < settings.MESSAGE_RATE_LIMIT:
        # Increment counter if under limit
        redis_client.incr(key)
        return False
    else:
        # Rate limit exceeded
        return True

def get_remaining_limit(phone_number: str) -> tuple[int, int]:
    """
    Get remaining messages allowed and time until reset

    Args:
        phone_number: The phone number to check

    Returns:
        tuple: (remaining_messages, seconds_until_reset)
    """
    key = f"rate_limit:{phone_number}"
    current_count = redis_client.get(key)
    ttl = redis_client.ttl(key)

    if current_count is None:
        return settings.MESSAGE_RATE_LIMIT, settings.MESSAGE_RATE_WINDOW

    remaining = max(0, settings.MESSAGE_RATE_LIMIT - int(current_count))
    return remaining, max(0, ttl)