# tasks.py
from celery import Celery
from dify_client import ChatClient
from decouple import config
from app.tasks.utils import send_message, logger, is_rate_limited, log_message, download_media_from_twilio
import requests
from typing import Optional, List, Dict
import tempfile
import os
from twilio.rest import Client

app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Initialize Twilio client
account_sid = config('TWILIO_ACCOUNT_SID')
auth_token = config('TWILIO_AUTH_TOKEN')
twilio_client = Client(account_sid, auth_token)

def get_dify_base_url():
    """Get base URL without trailing slash"""
    base_url = config('DIFY_BASE_URL').rstrip('/')
    if not base_url.endswith('/v1'):
        base_url = f"{base_url}/v1"
    return base_url

def upload_file_to_dify(media_content: bytes, content_type: str, user: str) -> Optional[Dict]:
    """Upload a file to Dify's file storage"""
    try:
        dify_key = config('DIFY_KEY')
        base_url = get_dify_base_url()
        upload_url = f"{base_url}/files/upload"

        # Create temporary file with proper extension
        extension = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp'
        }.get(content_type, '.jpg')

        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp_file:
            temp_file.write(media_content)
            temp_file_path = temp_file.name

        try:
            with open(temp_file_path, 'rb') as f:
                files = {'file': (f'image{extension}', f, content_type)}
                headers = {'Authorization': f'Bearer {dify_key}'}
                data = {'user': user}

                logger.info(f"Uploading file to Dify: {upload_url}")
                upload_response = requests.post(
                    upload_url,
                    headers=headers,
                    files=files,
                    data=data
                )
                upload_response.raise_for_status()

                # Log response for debugging
                logger.info(f"Dify upload response: {upload_response.text}")
                return upload_response.json()
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)

    except Exception as e:
        logger.error(f"Error uploading file to Dify: {str(e)}")
        if hasattr(e, 'response'):
            logger.error(f"Upload response content: {e.response.text}")
        return None

@app.task
def process_question(Body: str, From: str, media_items: Optional[List[Dict]] = None):
    """Process incoming WhatsApp message with optional media"""
    logger.info(f"Processing message - From: {From}, Media Items: {len(media_items) if media_items else 0}")

    try:
        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            send_message(From, "You have exceeded the message rate limit. Please try again later.")
            return

        dify_key = config("DIFY_KEY")
        base_url = get_dify_base_url()
        chat_url = f"{base_url}/chat-messages"

        # Format user identifier
        dify_user = From if From.startswith("whatsapp:") else f"whatsapp:{From.strip()}"

        # Get existing conversation
        conversation_id = None
        logger.info(f"Getting conversations from: {base_url}/conversations")
        conversations_response = requests.get(
            f"{base_url}/conversations",
            headers={'Authorization': f'Bearer {dify_key}'},
            params={'user': dify_user}
        )
        conversations_response.raise_for_status()
        conversations_data = conversations_response.json()

        if "data" in conversations_data:
            conversation_list = conversations_data.get("data")
            if conversation_list:
                conversation_id = conversation_list[0].get("id")

        # Process media if present
        uploaded_files = []
        if media_items:
            for item in media_items:
                media_content = download_media_from_twilio(item['url'])
                if media_content:
                    file_info = upload_file_to_dify(
                        media_content,
                        item['content_type'],
                        dify_user
                    )
                    if file_info:
                        # CHANGE 1: Simplify the file object to match Dify API requirements
                        uploaded_files.append({
                            'id': file_info['id'],
                            'type': 'image',  # Required enum value for images
                            'transfer_method': 'local_file'  # Required field
                        })
                        logger.info(f"File uploaded to Dify: {file_info['id']}")

        # Prepare message parameters
        message_params = {
            'query': Body or "Please analyze this image",
            'user': dify_user,
            'inputs': {},
            'files': uploaded_files,
            'response_mode': "blocking",  # or "streaming" if you prefer
            'conversation_id': conversation_id if conversation_id else None
        }

        if conversation_id:
            message_params['conversation_id'] = conversation_id

        # Send chat message
        logger.info(f"Sending chat message to: {chat_url}")
        logger.info(f"Message params: {message_params}")

        chat_response = requests.post(
            chat_url,
            headers={'Authorization': f'Bearer {dify_key}'},
            json=message_params
        )
        chat_response.raise_for_status()

        # Log response for debugging
        logger.info(f"Chat response: {chat_response.text}")

        result = chat_response.json().get("answer")

        if not result:
            raise ValueError("Empty response from Dify")

        # Send response back to user
        send_message(From, result)
        log_message(From, Body, result, "success")

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        if hasattr(e, 'response'):
            logger.error(f"Response content: {e.response.text}")
        log_message(From, Body, str(e), "error")
        error_msg = "Sorry, I encountered an error processing your message. Please try again later."
        send_message(From, error_msg)