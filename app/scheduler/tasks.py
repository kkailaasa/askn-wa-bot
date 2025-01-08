# tasks.py
from celery import Celery
from dify_client import ChatClient
from decouple import config
from app.tasks.utils import send_message, logger, is_rate_limited, log_message
import requests
from typing import Optional, List, Dict
import tempfile
import os

app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

def upload_file_to_dify(url: str, user: str) -> Optional[Dict]:
    """Upload a file from URL to Dify's file storage"""
    try:
        dify_base_url = config('DIFY_BASE_URL')
        dify_key = config('DIFY_KEY')
        upload_url = f"{dify_base_url}/files/upload"

        # Download file from Twilio URL
        response = requests.get(url, stream=True)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '')

        # Create temporary file with proper extension
        extension = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp'
        }.get(content_type, '.jpg')

        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        # Upload file to Dify
        try:
            with open(temp_file_path, 'rb') as f:
                files = {'file': (f'image{extension}', f, content_type)}
                headers = {'Authorization': f'Bearer {dify_key}'}
                data = {'user': user}

                upload_response = requests.post(
                    upload_url,
                    headers=headers,
                    files=files,
                    data=data
                )
                upload_response.raise_for_status()

                return upload_response.json()
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)

    except Exception as e:
        logger.error(f"Error uploading file to Dify: {str(e)}")
        return None

@app.task
def process_question(Body: str, From: str, media_items: Optional[List[Dict]] = None):
    """
    Process incoming WhatsApp message with optional media

    Args:
        Body: Message text
        From: Sender's phone number
        media_items: List of media items with URLs and types
    """
    logger.info(f"Processing message - From: {From}, Media Items: {len(media_items) if media_items else 0}")

    try:
        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            send_message(From, "You have exceeded the message rate limit. Please try again later.")
            return

        dify_key = config("DIFY_KEY")
        chat_client = ChatClient(dify_key)
        chat_client.base_url = config('DIFY_BASE_URL')

        # Format user identifier
        dify_user = From if From.startswith("whatsapp:") else f"whatsapp:{From.strip()}"

        # Get existing conversation
        conversation_id = None
        conversations = chat_client.get_conversations(user=dify_user)
        conversations.raise_for_status()

        if "data" in conversations.json():
            conversation_list = conversations.json().get("data")
            if conversation_list:
                conversation_id = conversation_list[0].get("id")

        # Process media if present
        uploaded_files = []
        if media_items:
            for item in media_items:
                file_info = upload_file_to_dify(item['url'], dify_user)
                if file_info:
                    uploaded_files.append({
                        'file_id': file_info['id'],
                        'type': 'image'
                    })
                    logger.info(f"File uploaded to Dify: {file_info['id']}")

        # Prepare message
        message_params = {
            'inputs': {},
            'query': Body or "Please analyze this image",
            'user': dify_user,
            'files': uploaded_files,
            'response_mode': "blocking"
        }

        if conversation_id:
            message_params['conversation_id'] = conversation_id

        # Send to Dify
        response = chat_client.create_chat_message(**message_params)
        response.raise_for_status()
        result = response.json().get("answer")

        if not result:
            raise ValueError("Empty response from Dify")

        # Send response back to user
        send_message(From, result)
        log_message(From, Body, result, "success")

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        log_message(From, Body, str(e), "error")
        error_msg = "Sorry, I encountered an error processing your message. Please try again later."
        send_message(From, error_msg)