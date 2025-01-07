# tasks.py
from celery import Celery
from dify_client import ChatClient
from decouple import config
from app.tasks.utils import send_message, logger, is_rate_limited, log_message

app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

@app.task
def process_question(Body: str, From: str):
    logger.info("Processing new message")
    dify_key = config("DIFY_KEY")
    chat_client = ChatClient(dify_key)

    try:
        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            send_message(From, "You have exceeded the message rate limit. Please try again later.")
            return

        chat_client.base_url = config('DIFY_BASE_URL')

        # Check for existing conversation
        conversation_id = None
        conversations = chat_client.get_conversations(user=From)
        conversations.raise_for_status()

        if "data" in conversations.json():
            conversation_list = conversations.json().get("data")
            if len(conversation_list) > 0:
                conversation_id = conversation_list[0].get("id")

        logger.info(f"Using conversation ID: {conversation_id}")

        # Process message
        if not conversation_id:
            response = chat_client.create_chat_message(inputs={}, query=Body, user=From, response_mode="blocking")
        else:
            response = chat_client.create_chat_message(
                inputs={},
                query=Body,
                user=From,
                conversation_id=conversation_id,
                response_mode="blocking"
            )

        response.raise_for_status()
        result = response.json().get("answer")
        logger.info(f"Sending response to {From}")

        # Log the interaction and send response
        log_message(From, Body, result, "success")
        send_message(From, result)

    except Exception as e:
        logger.error(f"Error processing message from {From}: {str(e)}")
        log_message(From, Body, str(e), "error")
        send_message(From, "Sorry, I encountered an error processing your message. Please try again later.")