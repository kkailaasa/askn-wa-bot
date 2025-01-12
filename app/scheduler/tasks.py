# tasks.py
from celery import Celery
from dify_client import ChatClient
from decouple import config
from app.tasks.utils import (
    send_message,
    logger,
    is_rate_limited,
    log_message,
    download_media_from_twilio,
    download_image_as_base64
)
import requests
from typing import Optional, List, Dict
import tempfile
import os
from twilio.rest import Client
import re
import json

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

def process_dify_response(response_text: str) -> Optional[dict]:
    """
    Process Dify response to extract message content and other relevant data

    Args:
        response_text: Raw SSE response text from Dify

    Returns:
        dict containing:
            - text: The main message content (from message or thought)
            - urls: List of image/media URLs
            - error: Any error message (if present)

    Handles both standard message events and agent_thought events.
    """
    try:
        # Split the response into individual SSE events
        events = response_text.strip().split('\n\n')
        result = {
            'text': '',
            'urls': [],
            'error': None
        }

        for event in events:
            if not event.startswith('data: '):
                continue

            try:
                data = json.loads(event[6:])  # Remove 'data: ' prefix

                # Extract regular message content
                if data.get('event') == 'message' or data.get('event') == 'agent_message':
                    answer = data.get('answer', '')
                    if answer:
                        # Append to existing text if we're getting streamed tokens
                        if result['text']:
                            result['text'] += answer
                        else:
                            result['text'] = answer

                # Extract thought content (which may contain the final response)
                elif data.get('event') == 'agent_thought':
                    thought = data.get('thought', '')
                    if thought:
                        # Replace existing text if this is a thought
                        # as thoughts typically contain the complete response
                        result['text'] = thought

                # Extract node output that might contain image URLs
                elif data.get('event') == 'node_finished':
                    node_data = data.get('data', {})
                    outputs = node_data.get('outputs', {})

                    # Check for errors in outputs
                    if outputs.get('status_code') == 400:
                        error_body = outputs.get('body', '')
                        if error_body:
                            try:
                                error_data = json.loads(error_body)
                                result['error'] = error_data.get('detail')
                            except json.JSONDecodeError:
                                result['error'] = error_body

                    # Check for files/media in outputs
                    files = outputs.get('files', [])
                    if files and isinstance(files, list):
                        for file in files:
                            if file.get('type') == 'image' and file.get('url'):
                                result['urls'].append(file['url'])

                # Check for workflow completion
                elif data.get('event') == 'workflow_finished':
                    workflow_data = data.get('data', {})
                    outputs = workflow_data.get('outputs', {})
                    if outputs.get('answer'):
                        result['text'] = outputs['answer']

                # Find URLs in text content and move them to urls list
                if result['text']:
                    url_pattern = r'https?://[^\s<"]+'
                    urls = re.findall(url_pattern, result['text'])

                    for url in urls:
                        # Check if URL is an image or Cloudflare storage URL
                        if (any(img_ext in url.lower() for img_ext in ['.png', '.jpg', '.jpeg', '.gif']) or
                            'cloudflarestorage.com' in url):
                            if url not in result['urls']:
                                result['urls'].append(url)
                            # Remove the URL from the text
                            result['text'] = result['text'].replace(url, '').strip()

            except json.JSONDecodeError:
                continue

        # Clean up text content
        result['text'] = ' '.join(result['text'].split())
        return result

    except Exception as e:
        logger.error(f"Error processing Dify response: {str(e)}")
        return None

def get_dify_base_url():
    """Get base URL without trailing slash"""
    base_url = config('DIFY_BASE_URL').rstrip('/')
    if not base_url.endswith('/v1'):
        base_url = f"{base_url}/v1"
    return base_url

def upload_file_to_nocodb(media_content: bytes, content_type: str, phone_number: str) -> Optional[Dict]:
    """Upload a file to NocoDB and return the signed URL"""
    try:
        base_url = config('NOCODB_BASE_URL').rstrip('/')
        api_token = config('NOCODB_API_TOKEN')
        table_id = config('NOCODB_TABLE_ID')

        # First, upload the file to NocoDB storage
        upload_url = f"{base_url}/api/v2/storage/upload"

        # Create a temporary file
        extension = '.jpg' if 'jpeg' in content_type else '.' + content_type.split('/')[-1]
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp_file:
            temp_file.write(media_content)
            temp_file_path = temp_file.name

        try:
            # Upload the file
            files = {
                'file': (f'image{extension}', open(temp_file_path, 'rb'), content_type)
            }
            headers = {
                'xc-token': api_token
            }

            logger.info(f"Uploading file to NocoDB storage: {upload_url}")
            upload_response = requests.post(
                upload_url,
                headers=headers,
                files=files
            )
            upload_response.raise_for_status()

            file_data = upload_response.json()
            logger.info(f"File upload response: {file_data}")

            if not file_data or not isinstance(file_data, list) or not file_data[0].get('url'):
                raise ValueError("Invalid upload response format")

            file_url = file_data[0]['url']

            # Now create the record with the URL
            create_url = f"{base_url}/api/v2/tables/{table_id}/records"
            record_data = {
                "phone_number": phone_number,
                "profile_photo": [{
                    "url": file_url,
                    "title": f"image_{phone_number}",
                    "mimetype": content_type,
                    "size": len(media_content)
                }]
            }

            logger.info(f"Creating record in NocoDB: {create_url}")
            record_response = requests.post(
                create_url,
                headers={'xc-token': api_token, 'Content-Type': 'application/json'},
                json=record_data
            )
            record_response.raise_for_status()
            record_data = record_response.json()

            record_id = record_data.get('Id')
            if not record_id:
                raise ValueError("No record ID in response")

            get_url = f"{base_url}/api/v2/tables/{table_id}/records/{record_id}"
            get_response = requests.get(
                get_url,
                headers={'xc-token': api_token}
            )
            get_response.raise_for_status()
            get_data = get_response.json()

            if not get_data.get('profile_photo') or not get_data['profile_photo'][0].get('signedUrl'):
                raise ValueError("No signed URL in record")

            signed_url = get_data['profile_photo'][0]['signedUrl']
            logger.info(f"Got signed URL: {signed_url}")

            return {"url": signed_url}

        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)

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
                        uploaded_files.append({
                            'type': 'image',
                            'transfer_method': 'remote_url',
                            'url': file_info['url']
                        })
                        logger.info(f"File uploaded to NocoDB with URL: {file_info['url']}")

        # Construct query
        query_parts = [f"User {dify_user}:"]
        if Body:
            query_parts.append(Body)
        if uploaded_files:
            for file_info in uploaded_files:
                if file_info.get('url'):
                    query_parts.append(f"Image URL: {file_info['url']}")

        modified_query = " ".join(query_parts)

        # Prepare message parameters
        message_params = {
            'query': modified_query,
            'user': dify_user,
            'inputs': {},
            'files': uploaded_files,
            'response_mode': "streaming",
            'conversation_id': conversation_id if conversation_id else None
        }

        logger.info(f"Sending chat message to: {chat_url}")
        logger.info(f"Message params: {message_params}")

        # Make request to Dify
        chat_response = requests.post(
            chat_url,
            headers={'Authorization': f'Bearer {dify_key}'},
            json=message_params,
            stream=True
        )
        chat_response.raise_for_status()

        # Accumulate streaming response
        full_response = ''
        for line in chat_response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                full_response += decoded_line + '\n\n'

        logger.info("Processing full response")
        result = process_dify_response(full_response)

        if not result:
            raise ValueError("No valid response content found in Dify response")

        if result.get('error'):
            raise ValueError(f"Error in Dify response: {result['error']}")

        # Send message with media URLs if available
        if result['urls']:
            logger.info(f"Sending message with {len(result['urls'])} media attachments")
            send_message(From, result['text'], result['urls'])
        else:
            logger.info("Sending text-only message")
            send_message(From, result['text'])

        log_message(From, Body, result['text'], "success")

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        if hasattr(e, 'response'):
            logger.error(f"Response content: {e.response.text}")
        log_message(From, Body, str(e), "error")
        error_msg = "Sorry, I encountered an error processing your message. Please try again later."
        send_message(From, error_msg)