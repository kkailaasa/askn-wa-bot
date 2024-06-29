import logging
import redis
from twilio.rest import Client
from decouple import config

# Twilio configuration
account_sid = config('TWILIO_ACCOUNT_SID')
auth_token = config('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)
twilio_number = config('TWILIO_NUMBER')

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_message(to_number, body_text):
    try:
        # Ensure the to_number is properly formatted for WhatsApp
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        message = client.messages.create(
            from_=f"whatsapp:{twilio_number}",
            body=body_text,
            to=to_number
        )
        logger.info(f"Message sent to {to_number}: {message.body}")
    except Exception as e:
        logger.error(f"Error sending message to {to_number}: {e}")
        raise e  # Reraise the exception to be handled by the calling function


# redis rate limiting

redis_client = redis.StrictRedis(host='localhost', port=6379)

RATE_LIMIT = 2 # NO OF MESSAGES PER NUMBER 
TIME_WINDOW = 60 # IN SECONDS

def is_rate_limited(phone_number):
    key = f"rate_limit:{phone_number}"
    current_count = redis_client.get(key)

    if current_count is None:
        # Initialize the count & set expiry
        redis_client.setex(key, TIME_WINDOW, 1)
        return False
    elif int(current_count) < RATE_LIMIT:
        # Increment
        redis_client.incr(key)
        return False
    else:
        # rate exceeded
        return True


