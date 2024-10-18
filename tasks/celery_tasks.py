from celery import Celery
from services.dify_chat import ChatService
from services.twilio_auth import MessagingService
from utils.redis_helpers import is_rate_limited
from utils.redis_pool import get_redis_client
from core.config import settings
import logging
import traceback
import time

logger = logging.getLogger(__name__)

# Initialize the Celery app
app = Celery('tasks', broker=settings.REDIS_URL, backend=settings.REDIS_URL)

app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

chat_service = ChatService()
messaging_service = MessagingService()

# Use the connection pool
redis_client = get_redis_client()

@app.task
def process_question(Body: str, From: str):
    # Your existing task code here
    pass

@app.task
def cleanup_redis_data():
    logger.info("Starting Redis data cleanup task")
    current_time = int(time.time())
    
    try:
        # Cleanup temporary data
        temp_data_pattern = "temp_data:*"
        for key in redis_client.scan_iter(temp_data_pattern):
            if redis_client.ttl(key) < 0:  # If TTL is negative, the key has no expiry set
                redis_client.delete(key)
        
        # Cleanup rate limiting data
        rate_limit_pattern = "rate_limit:*"
        for key in redis_client.scan_iter(rate_limit_pattern):
            redis_client.zremrangebyscore(key, 0, current_time - 86400)  # Remove entries older than 24 hours
        
        # Cleanup OTP data
        otp_pattern = "otp:*"
        for key in redis_client.scan_iter(otp_pattern):
            if redis_client.ttl(key) < 0:  # If TTL is negative, the key has no expiry set
                redis_client.delete(key)
        
        logger.info("Redis data cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during Redis data cleanup: {str(e)}")
        logger.error(traceback.format_exc())

# Update Celery beat schedule to include the cleanup task
app.conf.beat_schedule = {
    'cleanup-redis-data': {
        'task': 'tasks.celery_tasks.cleanup_redis_data',
        'schedule': 3600.0,  # Run every hour
    },
}