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

def send_media_message(to_number, media_url, caption=None):
    """
    Send a media message via Twilio WhatsApp using a direct URL.
    
    Args:
        to_number (str): The recipient's phone number
        media_url (str): URL of the media file
        caption (str, optional): Optional caption to include with the media
    """
    try:
        # Ensure the to_number is properly formatted for WhatsApp
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"
            
        # Prepare message parameters
        message_params = {
            'from_': f"whatsapp:{twilio_number}",
            'media_url': [media_url],
            'to': to_number
        }
        
        # Add caption if provided
        if caption:
            message_params['body'] = caption
            
        # Send the message
        message = client.messages.create(**message_params)
        logger.info(f"Media message sent to {to_number} with media {media_url}")
    except Exception as e:
        logger.error(f"Error sending media message to {to_number}: {e}")
        raise e  # Reraise the exception to be handled by the calling function


# redis rate limiting

redis_client = redis.StrictRedis(host='redis', port=6379)

RATE_LIMIT = 9 # NO OF MESSAGES PER NUMBER
TIME_WINDOW = 3600 # IN SECONDS

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