from celery import Celery
from services.ecitizen_auth import is_user_authorized
from services.dify_chat import ChatService
from services.twillio_auth import MessagingService
from utils.redis_helpers import is_rate_limited
import logging

logger = logging.getLogger(__name__)

app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')
app.conf.update(
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
        if not is_user_authorized(From):
            logger.info(f"User not present with phone number {From}")
            messaging_service.send_message(From, "Signup to continue chatting with Ask Nithyananda, please visit +1 2518100108")
            return

        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            return

        conversation_id = chat_service.get_conversation_id(From)
        result = chat_service.create_chat_message(From, Body, conversation_id)

        logger.info(f"The response to be sent was {result}")
        messaging_service.send_message(From, result)

    except Exception as e:
        logger.error(f"Error processing message for {From}: {str(e)}")