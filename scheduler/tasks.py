import time
import requests
import re
import os
from typing import Optional, Tuple, List
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

def download_image(url: str) -> Tuple[bool, Optional[str]]:
    """
    Download an image from a URL and save it temporarily.

    Args:
        url: URL of the image to download

    Returns:
        Tuple of (success, file_path)
    """
    try:
        # Create a temporary directory if it doesn't exist
        temp_dir = "/tmp/dify_images"
        os.makedirs(temp_dir, exist_ok=True)

        # Generate a filename based on timestamp
        filename = f"{temp_dir}/image_{int(time.time())}.jpg"

        # Download the image
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()

        # Save the image
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return True, filename
    except Exception as e:
        logger.error(f"Failed to download image from {url}: {str(e)}")
        return False, None

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

    # Images found, process them
    for url in image_urls:
        # Download the image
        success, image_path = download_image(url)
        if success:
            # Clean the text to remove the image URL
            cleaned_text = response_text.replace(url, "").strip()

            # Send the image with caption (if cleaned text exists)
            if cleaned_text:
                send_media_message(From, image_path, cleaned_text)
            else:
                send_media_message(From, image_path)

            # Clean up the temporary file
            try:
                os.remove(image_path)
            except OSError:
                pass
        else:
            # If image download failed, just send the text
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