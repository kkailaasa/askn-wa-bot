import openai
import time
import requests
from typing import Optional
from celery import Celery
from dify_client import ChatClient
from fastapi import FastAPI, Form
from decouple import config
from utils import send_message, logger, is_rate_limited
from auth import is_user_authorized

app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

def get_active_conversation(chat_client: ChatClient, From: str) -> Optional[str]:
    """
    Get the conversation ID if there's an active conversation less than 1 hour old

    Args:
        chat_client: ChatClient instance
        From: User identifier

    Returns:
        str: Conversation ID if found and active, None otherwise
    """
    try:
        conversations = chat_client.get_conversations(user=From)
        conversations.raise_for_status()

        if "data" in conversations.json():
            conversation_list = conversations.json().get("data")
            if len(conversation_list) > 0:
                latest_conversation = conversation_list[0]
                updated_at = latest_conversation.get("updated_at", 0)

                # Check if conversation is less than 1 hour old
                current_time = int(time.time())
                one_hour = 3600  # seconds

                if (current_time - updated_at) < one_hour:
                    return latest_conversation.get("id")

        return None
    except Exception as e:
        logger.error(f"Error getting active conversation: {str(e)}")
        return None

@app.task
def process_question(Body: str, From: str):
    logger.info("dify called")
    dify_key = config("DIFY_KEY")
    chat_client = ChatClient(dify_key)
    try:
        if not is_user_authorized(From):
            logger.info(f"user not present with phone number ${From}")
            send_message(From, "Signup to continue chating with Ask Nithyananda, please visit +1 2518100108")
            return

        if is_rate_limited(From):
            logger.info(f"rate limit exceed for ${From}")
            send_message(From, "You have reached your message limit. Please try again later.")
            return

        chat_client.base_url = "http://brightpath.koogle.sk/v1"

        # Get active conversation (less than 1 hour old)
        conversation_id = get_active_conversation(chat_client, From)
        logger.info(f"Active conversation id was {conversation_id}")

        if not conversation_id:
            # If no active conversation exists, create a new one
            response = chat_client.create_chat_message(
                inputs={},
                query=Body,
                user=From,
                response_mode="blocking"
            )
            response.raise_for_status()
            result = response.json().get("answer")
            logger.info(f"The response to be sent was {result}")
            # Send message back to the sender's number
            send_message(From, result)
        else:
            # Continue the conversation by including the conversation_id
            response = chat_client.create_chat_message(
                inputs={},
                query=Body,
                user=From,
                conversation_id=conversation_id,
                response_mode="blocking"
            )
            response.raise_for_status()
            result = response.json().get("answer")
            logger.info(f"The response to be sent was {result}")
            # Send message back to the sender's number
            send_message(From, result)
    except Exception as e:
        logger.error(f"Error sending message to {From}: {str(e)}")