from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from core.config import settings
import logging
from urllib.parse import urlparse
from utils.http_client import http_pool

class CustomTwilioHttpClient(TwilioHttpClient):
    def __init__(self):
        super().__init__()
        self.pool = http_pool.get_pool(
            host='api.twilio.com',
            maxsize=settings.TWILIO_MAX_CONNECTIONS
        )
    
    def request(self, method, url, params=None, data=None, headers=None, auth=None, timeout=None):
        return self.pool.request(
            method=method,
            url=url,
            fields=data,
            headers=headers,
            timeout=timeout
        )

class MessagingService:
    def __init__(self):
        http_client = CustomTwilioHttpClient()
        self.client = Client(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            http_client=http_client
        )
        self.twilio_number = settings.TWILIO_NUMBER
        self.logger = logging.getLogger(__name__)

    def send_message(self, to_number: str, body_text: str):
        try:
            # Ensure the number has the whatsapp: prefix
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"

            from_number = f"whatsapp:{self.twilio_number}"

            self.logger.debug(f"Sending message - To: {to_number}, From: {from_number}, Body: {body_text}")

            message = self.client.messages.create(
                from_=from_number,
                body=body_text,
                to=to_number
            )

            self.logger.info(f"Message sent successfully - SID: {message.sid}")
            self.logger.debug(f"Complete message object: {message}")

            return message.sid
        except Exception as e:
            self.logger.error(f"Error sending message: {str(e)}", exc_info=True)
            raise