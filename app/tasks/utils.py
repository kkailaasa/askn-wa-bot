# utils.py
import logging
import redis
import requests
import base64
from twilio.rest import Client
from decouple import config
from app.db.models import MessageLog
from app.db.database import SessionLocal
from typing import Optional, List, Dict, Union

# Twilio configuration
account_sid = config('TWILIO_ACCOUNT_SID')
auth_token = config('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)
twilio_number = config('TWILIO_NUMBER')

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app_data/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def log_message(phone_number: str, message: str, response: str, status: str):
    db = SessionLocal()
    try:
        log_entry = MessageLog(
            phone_number=phone_number,
            message=message,
            response=response,
            status=status
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Error logging message: {e}")
        db.rollback()
    finally:
        db.close()

def send_message(
    to_number: str,
    body_text: Optional[str] = None,
    media_url: Optional[Union[str, List[str]]] = None
) -> Optional[str]:
    """
    Send a WhatsApp message with optional media
    """
    try:
        # Validate at least one of body or media is present
        if not body_text and not media_url:
            logger.error("Both message body and media are empty")
            return None

        # Format WhatsApp number correctly
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number.strip()}"
        else:
            parts = to_number.split(":")
            to_number = f"{parts[0]}:{parts[1].strip()}"

        # Prepare message parameters
        message_params = {
            'from_': f"whatsapp:{twilio_number.strip()}",
            'to': to_number
        }

        # Add body if present
        if body_text and body_text.strip():
            message_params['body'] = body_text

        # Add media if present, properly handling URL encoding
        if media_url:
            if isinstance(media_url, str):
                media_url = [media_url]

            # Try to pre-validate and encode URLs
            valid_urls = []
            for url in media_url:
                try:
                    # First try to download or at least validate the URL
                    response = requests.head(url, allow_redirects=True, timeout=5)
                    response.raise_for_status()
                    final_url = response.url  # Get the final URL after any redirects
                    valid_urls.append(final_url)
                    logger.info(f"Successfully validated media URL: {final_url}")
                except Exception as e:
                    logger.error(f"Failed to validate media URL {url}: {str(e)}")
                    # If URL validation fails, try sending message without media
                    continue

            if valid_urls:
                message_params['media_url'] = valid_urls
            elif body_text:  # If no valid URLs but we have text, send text-only message
                logger.warning("No valid media URLs found, sending text-only message")
            else:
                raise ValueError("No valid media URLs and no message text")

        # Send message
        message = client.messages.create(**message_params)

        logger.info(f"Message sent to {to_number} - SID: {message.sid}")
        log_message(
            to_number,
            f"Body: {body_text}, Media: {valid_urls if media_url else None}",
            f"Message SID: {message.sid}",
            "success"
        )
        return message.sid

    except Exception as e:
        logger.error(f"Error sending message to {to_number}: {e}")
        # Attempt to send text-only message if media fails
        if body_text and media_url:
            logger.info("Attempting to send text-only message after media failure")
            try:
                message = client.messages.create(
                    from_=f"whatsapp:{twilio_number.strip()}",
                    to=to_number,
                    body=body_text
                )
                log_message(to_number, body_text, f"Fallback message SID: {message.sid}", "success")
                return message.sid
            except Exception as fallback_error:
                logger.error(f"Fallback message also failed: {fallback_error}")

        log_message(to_number, body_text or "", str(e), "error")
        raise e

# Redis rate limiting
redis_client = redis.StrictRedis(host='redis', port=6379)
RATE_LIMIT = config('RATE_LIMIT', default=2, cast=int)
TIME_WINDOW = config('TIME_WINDOW', default=60, cast=int)

def is_rate_limited(phone_number: str) -> bool:
    """Check if a phone number has exceeded rate limits"""
    key = f"rate_limit:{phone_number}"
    current_count = redis_client.get(key)

    if current_count is None:
        redis_client.setex(key, TIME_WINDOW, 1)
        return False
    elif int(current_count) < RATE_LIMIT:
        redis_client.incr(key)
        return False
    else:
        log_message(phone_number, "", "Rate limit exceeded", "rate_limited")
        return True

def get_mime_type(file_extension: str) -> Optional[str]:
    """Get MIME type for common WhatsApp supported formats"""
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp',
        'pdf': 'application/pdf',
        'mp3': 'audio/mpeg',
        'mp4': 'video/mp4',
        'ogg': 'audio/ogg',
        'amr': 'audio/amr',
        'vcf': 'text/x-vcard'
    }
    return mime_types.get(file_extension.lower())

def download_media_from_twilio(media_url: str) -> Optional[bytes]:
    """
    Download media content from Twilio's media URL

    Args:
        media_url: The URL of the media to download

    Returns:
        Optional[bytes]: The media content as bytes if successful, None otherwise
    """
    try:
        # Get media content using Twilio client credentials
        response = requests.get(
            media_url,
            auth=(account_sid, auth_token),
            stream=True
        )
        response.raise_for_status()

        # Read and return the content
        return response.content

    except Exception as e:
        logger.error(f"Error downloading media from Twilio: {str(e)}")
        return None

def download_image_as_base64(url: str) -> Optional[str]:
    """Download image from URL and convert to base64 string"""
    try:
        response = requests.get(url)
        response.raise_for_status()

        # Convert to base64
        image_base64 = base64.b64encode(response.content).decode('utf-8')

        # Get file extension from URL
        extension = url.split('.')[-1].split('?')[0].lower()
        if extension in ['jpg', 'jpeg']:
            mime_type = 'image/jpeg'
        elif extension == 'png':
            mime_type = 'image/png'
        else:
            mime_type = 'image/jpeg'  # default to jpeg

        return f"data:{mime_type};base64,{image_base64}"
    except Exception as e:
        logger.error(f"Error converting image to base64: {str(e)}")
        return None