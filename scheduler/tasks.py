import time
import requests
import re
from typing import Optional, List
from celery import Celery
from dify_client import ChatClient
from fastapi import FastAPI, Form
from decouple import config
from utils import send_message, send_media_message, logger, is_rate_limited
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

def extract_image_urls(text: str) -> List[str]:
    """
    Extract image URLs from text that appear to be JPEG/JPG images.
    
    Args:
        text: Text that might contain image URLs
        
    Returns:
        List of image URLs found
    """
    # Pattern to match URLs ending with .jpg, .jpeg (case insensitive)
    url_pattern = r'https?://\S+\.jpe?g\b'
    return re.findall(url_pattern, text, re.IGNORECASE)

def process_and_send_response(From: str, response_text: str):
    """
    Process the response text, extract any images, and send them appropriately.
    
    Args:
        From: Recipient's phone number
        response_text: Text response from Dify
    """
    # Extract image URLs from the response
    image_urls = extract_image_urls(response_text)
    
    if not image_urls:
        # No images found, just send the text
        send_message(From, response_text)
        return
    
    # If only one image is found, send it with the text as caption
    if len(image_urls) == 1:
        image_url = image_urls[0]
        # Clean the text to remove the image URL
        cleaned_text = response_text.replace(image_url, "").strip()
        
        try:
            # Send the image with caption
            send_media_message(From, image_url, cleaned_text if cleaned_text else None)
            logger.info(f"Sent media message with URL: {image_url}")
        except Exception as e:
            logger.error(f"Failed to send media message: {str(e)}")
            # Fallback to text-only message
            send_message(From, response_text)
    else:
        # Multiple images - currently Twilio can only send one media per message
        # So we'll send the first image with text and then the rest separately
        first_url = image_urls[0]
        # Remove all URLs from the text
        cleaned_text = response_text
        for url in image_urls:
            cleaned_text = cleaned_text.replace(url, "").strip()
        
        try:
            # Send first image with cleaned text
            send_media_message(From, first_url, cleaned_text if cleaned_text else None)
            
            # Send remaining images separately
            for url in image_urls[1:]:
                send_media_message(From, url)
        except Exception as e:
            logger.error(f"Failed to send multiple media messages: {str(e)}")
            # Fallback to text-only message
            send_message(From, response_text)

@app.task
def process_question(Body: str, From: str):
    logger.info("dify called")
    dify_key = config("DIFY_KEY")
    chat_client = ChatClient(dify_key)
    try:
        if not is_user_authorized(From):
            logger.info(f"user not present with phone number ${From}")
            send_message(From, "Signup to continue chating with Ask Nithyananda AI, please visit +12518100108")
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
            # Process and send the response (text and/or images)
            process_and_send_response(From, result)
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
            # Process and send the response (text and/or images)
            process_and_send_response(From, result)
    except Exception as e:
        logger.error(f"Error processing message for {From}: {str(e)}")
        # Send fallback message in case of error
        try:
            send_message(From, "I'm sorry, but I encountered an error processing your request. Please try again later.")
        except:
            logger.error(f"Failed to send fallback message to {From}")