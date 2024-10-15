from celery import Celery
from services.dify_chat import ChatService
from services.twillio_auth import MessagingService
from utils.redis_helpers import is_rate_limited
from core.config import settings
import logging
import traceback

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

@app.task
def process_question(Body: str, From: str):
    logger.info("Processing question")
    try:
        # Remove 'whatsapp:' prefix from the phone number
        From = From.replace('whatsapp:', '')

        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            return

        conversation_id = chat_service.get_conversation_id(From)
        result = chat_service.create_chat_message(From, Body, conversation_id)

        logger.info(f"The response to be sent was {result}")
        messaging_service.send_message(From, result)

    except Exception as e:
        logger.error(f"Error processing message for {From}: {str(e)}")
        logger.error(traceback.format_exc())
        # Optionally, send an error message to the user
        messaging_service.send_message(From, "Sorry, an error occurred while processing your message. Please try again later.")