# utils.py
import logging
import redis
from twilio.rest import Client
from decouple import config
from app.db.models import MessageLog
from app.db.database import SessionLocal

# Twilio configuration
account_sid = config('TWILIO_ACCOUNT_SID')
auth_token = config('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)
twilio_number = config('TWILIO_NUMBER')

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app_data/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def log_message(phone_number, message, response, status):
    db = SessionLocal()
    try:
        log_entry = MessageLog(
            phone_number=phone_number,
            message=message,
            response=response,
            status=status
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Error logging message: {e}")
        db.rollback()
    finally:
        db.close()

def send_message(to_number, body_text):
    try:
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        message = client.messages.create(
            from_=f"whatsapp:{twilio_number}",
            body=body_text,
            to=to_number
        )
        logger.info(f"Message sent to {to_number}: {message.body}")
        log_message(to_number, "", body_text, "success")
        return message
    except Exception as e:
        logger.error(f"Error sending message to {to_number}: {e}")
        log_message(to_number, "", str(e), "error")
        raise e

# Redis rate limiting
redis_client = redis.StrictRedis(host='redis', port=6379)
RATE_LIMIT = config('RATE_LIMIT', default=2, cast=int)
TIME_WINDOW = config('TIME_WINDOW', default=60, cast=int)

def is_rate_limited(phone_number):
    key = f"rate_limit:{phone_number}"
    current_count = redis_client.get(key)

    if current_count is None:
        redis_client.setex(key, TIME_WINDOW, 1)
        return False
    elif int(current_count) < RATE_LIMIT:
        redis_client.incr(key)
        return False
    else:
        log_message(phone_number, "", "Rate limit exceeded", "rate_limited")
        return True