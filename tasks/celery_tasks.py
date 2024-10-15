from celery import Celery
# from services.ecitizen_auth import is_user_authorized
from services.dify_chat import ChatService
from services.twillio_auth import MessagingService
from utils.redis_helpers import is_rate_limited
from config import settings
import logging
import traceback

logger = logging.getLogger(__name__)

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
        # Strip 'whatsapp:' prefix if present
        user_id = From.split(':')[-1] if ':' in From else From

        #Authorization Celery Task
        #if not is_user_authorized(user_id):
        #    logger.info(f"User not present with phone number {user_id}")
        #    messaging_service.send_message(From, "Signup to continue chatting with Ask Nithyananda, please visit +1 2518100108")
        #    return

        if is_rate_limited(user_id):  # Changed From to user_id
            logger.info(f"Rate limit exceeded for {user_id}")
            return

        conversation_id = chat_service.get_conversation_id(user_id)  # Changed From to user_id
        result = chat_service.create_chat_message(user_id, Body, conversation_id)  # Changed From to user_id

        logger.info(f"The response to be sent was {result}")
        messaging_service.send_message(From, result)  # Keep original From for Twilio

    except Exception as e:
        logger.error(f"Error processing message for {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        # Optionally, send an error message to the user
        messaging_service.send_message(From, "Sorry, an error occurred while processing your message. Please try again later.")