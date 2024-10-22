from celery import Celery
from core.config import settings
import logging
from services import ChatService, MessagingService
from utils.redis_pool import get_redis_client
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Celery app
celery_app = Celery('tasks', 
                   broker=settings.REDIS_URL,
                   backend=settings.REDIS_URL)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

@celery_app.task
def process_question(Body: str, From: str):
    logger.info(f"Processing question: {Body} from {From}")
    chat_service = ChatService()
    messaging_service = MessagingService()

    try:
        # Get or create a conversation
        conversation_id = chat_service.get_conversation_id(From)

        # Generate a response using Dify
        response = chat_service.create_chat_message(From, Body, conversation_id)

        # Send the response back to the user via Twilio
        messaging_service.send_message(From, response)

        logger.info(f"Successfully processed and responded to message from {From}")
    except Exception as e:
        logger.error(f"Error processing message from {From}: {str(e)}")
        # Send an error message to the user
        error_message = "Sorry, an error occurred while processing your message. Please try again later."
        messaging_service.send_message(From, error_message)

@celery_app.task
def cleanup_redis_data():
    logger.info("Starting Redis data cleanup task")
    redis_client = get_redis_client()

    try:
        # Clean up expired OTPs
        otp_pattern = "otp:*"
        otp_keys = redis_client.keys(otp_pattern)
        expired_otps = [key for key in otp_keys if redis_client.ttl(key) <= 0]
        if expired_otps:
            redis_client.delete(*expired_otps)
            logger.info(f"Cleaned up {len(expired_otps)} expired OTPs")

        # Clean up temporary data
        temp_data_pattern = "temp_data:*"
        temp_data_keys = redis_client.keys(temp_data_pattern)
        current_time = int(time.time())
        expired_temp_data = []

        for key in temp_data_keys:
            if current_time - int(redis_client.get(key).decode('utf-8').split(':')[0]) > 3600:
                expired_temp_data.append(key)

        if expired_temp_data:
            redis_client.delete(*expired_temp_data)
            logger.info(f"Cleaned up {len(expired_temp_data)} expired temporary data entries")

        logger.info("Redis data cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during Redis cleanup: {str(e)}")

celery_app.conf.beat_schedule = {
    'cleanup-redis-data': {
        'task': 'tasks.celery_tasks.cleanup_redis_data',
        'schedule': 3600.0,  # Run every hour
    },
}