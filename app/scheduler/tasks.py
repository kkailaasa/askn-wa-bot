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

def upload_file_to_nocodb(media_content: bytes, content_type: str, phone_number: str) -> Optional[Dict]:
    """Upload a file to NocoDB and return the public URL"""
    try:
        base_url = config('NOCODB_BASE_URL').rstrip('/')
        api_token = config('NOCODB_API_TOKEN')
        table_id = config('NOCODB_TABLE_ID')

        # Upload to NocoDB
        headers = {
            'xc-token': api_token,
            'Content-Type': 'application/json'
        }

        # Convert the media content to base64 for temporary storage
        import base64
        base64_content = base64.b64encode(media_content).decode('utf-8')

        # Create the record with the base64 content
        create_url = f"{base_url}/api/v2/tables/{table_id}/records"

        data = {
            "phone_number": phone_number,
            "profile_photo": [{
                "data": f"data:{content_type};base64,{base64_content}",
                "mimetype": content_type,
                "title": f"image_{phone_number}"
            }]
        }

        logger.info(f"Creating record in NocoDB for {phone_number}")
        response = requests.post(
            create_url,
            headers=headers,
            json=data
        )
        response.raise_for_status()

        # Get the URL from the response
        record_data = response.json()
        if record_data and 'profile_photo' in record_data and record_data['profile_photo']:
            public_url = record_data['profile_photo'][0]['url']

            # Update record with public URL
            record_id = record_data['Id']
            update_url = f"{base_url}/api/v2/tables/{table_id}/records/{record_id}"
            update_data = {"public_url": public_url}

            requests.patch(
                update_url,
                headers=headers,
                json=update_data
            )

            logger.info(f"File uploaded to NocoDB: {public_url}")
            return {"url": public_url}

        raise ValueError("No URL in NocoDB response")

    except Exception as e:
        logger.error(f"Error uploading file to NocoDB: {str(e)}")
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
                    file_info = upload_file_to_nocodb(
                        media_content,
                        item['content_type'],
                        dify_user
                    )
                    if file_info and 'url' in file_info:
                        # Use the NocoDB public URL for Dify
                        uploaded_files.append({
                            'type': 'image',
                            'transfer_method': 'url',
                            'url': file_info['url']
                        })
                        logger.info(f"File uploaded to NocoDB with URL: {file_info['url']}")

        # Prepare message parameters
        message_params = {
            'query': Body or "Please analyze this image",
            'user': dify_user,
            'inputs': {},
            'files': uploaded_files,
            'response_mode': "blocking",
            'conversation_id': conversation_id if conversation_id else None
        }

        # Log the parameters for debugging
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