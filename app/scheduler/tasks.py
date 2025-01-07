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

async def upload_file_to_dify(url: str, user: str) -> Optional[Dict]:
    """
    Upload a file from URL to Dify's file storage
    Returns file info if successful, None if failed
    """
    try:
        dify_base_url = config('DIFY_BASE_URL')
        dify_key = config('DIFY_KEY')
        upload_url = f"{dify_base_url}/files/upload"

        # Download file from Twilio URL to temporary file
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

async def process_media_items(media_items: List[Dict], user: str) -> List[Dict]:
    """Process media items and upload to Dify"""
    uploaded_files = []

    for item in media_items:
        url = item.get('url')
        if not url:
            continue

        file_info = await upload_file_to_dify(url, user)
        if file_info:
            uploaded_files.append({
                'file_id': file_info['id'],
                'type': 'image'
            })
            logger.info(f"Successfully uploaded file to Dify: {file_info['id']}")

    return uploaded_files

@app.task
async def process_question(Body: str, From: str, media_items: Optional[List[Dict]] = None):
    logger.info("Processing new message")
    dify_key = config("DIFY_KEY")
    chat_client = ChatClient(dify_key)

    try:
        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            send_message(From, "You have exceeded the message rate limit. Please try again later.")
            return

        chat_client.base_url = config('DIFY_BASE_URL')
        dify_user = From if From.startswith("whatsapp:") else f"whatsapp:{From.strip()}"

        # Upload media files if present
        uploaded_files = []
        if media_items:
            uploaded_files = await process_media_items(media_items, dify_user)
            if not uploaded_files:
                logger.warning("Failed to upload media files to Dify")

        # Get conversation ID
        conversation_id = None
        conversations = chat_client.get_conversations(user=dify_user)
        conversations.raise_for_status()

        if "data" in conversations.json():
            conversation_list = conversations.json().get("data")
            if len(conversation_list) > 0:
                conversation_id = conversation_list[0].get("id")

        logger.info(f"Using conversation ID: {conversation_id}")

        # Prepare message with file references
        message_params = {
            'inputs': {},
            'query': Body or "Please analyze this image",
            'user': dify_user,
            'files': uploaded_files,
            'response_mode': "blocking"
        }

        if conversation_id:
            message_params['conversation_id'] = conversation_id

        # Send message to Dify
        response = chat_client.create_chat_message(**message_params)
        response.raise_for_status()

        result = response.json().get("answer")

        # Validate response
        if not result:
            raise ValueError("Empty response from Dify")

        logger.info(f"Sending response to {From}")

        # Log the interaction and send response
        log_message(From, Body, result, "success")
        send_message(From, result)

    except Exception as e:
        logger.error(f"Error processing message from {From}: {str(e)}")
        log_message(From, Body, str(e), "error")
        error_msg = "Sorry, I encountered an error processing your message. Please try again later."
        send_message(From, error_msg)