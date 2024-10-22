# tasks/celery_tasks.py
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
                   broker=settings.CELERY_BROKER_URL,
                   backend=settings.CELERY_RESULT_BACKEND)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

@celery_app.task(bind=True, max_retries=3)
def process_question(self, Body: str, From: str):
    logger.info(f"Processing question: {Body} from {From}")
    try:
        chat_service = ChatService()
        messaging_service = MessagingService()

        # Get or create a conversation
        conversation_id = chat_service.get_conversation_id(From)

        # Generate a response using Dify
        response = chat_service.create_chat_message(From, Body, conversation_id)

        # Send the response back to the user via Twilio
        messaging_service.send_message(From, response)

        logger.info(f"Successfully processed and responded to message from {From}")
    except Exception as e:
        logger.error(f"Error processing message from {From}: {str(e)}")
        # Retry task with exponential backoff
        retry_in = (self.request.retries + 1) * 60  # 60s, 120s, 180s
        raise self.retry(exc=e, countdown=retry_in)

@celery_app.task
def cleanup_redis_data():
    logger.info("Starting Redis data cleanup task")
    try:
        redis_client = get_redis_client()

        # Clean up expired OTPs
        otp_pattern = "otp:*"
        otp_keys = redis_client.keys(otp_pattern)
        if otp_keys:
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
            try:
                if current_time - int(redis_client.get(key).decode('utf-8').split(':')[0]) > 3600:
                    expired_temp_data.append(key)
            except (ValueError, AttributeError, IndexError) as e:
                logger.warning(f"Error processing key {key}: {str(e)}")
                continue

        if expired_temp_data:
            redis_client.delete(*expired_temp_data)
            logger.info(f"Cleaned up {len(expired_temp_data)} expired temporary data entries")

        logger.info("Redis data cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during Redis cleanup: {str(e)}")

# Configure periodic tasks
celery_app.conf.beat_schedule = {
    'cleanup-redis-data': {
        'task': 'tasks.celery_tasks.cleanup_redis_data',
        'schedule': 3600.0,  # Run every hour
    },
}