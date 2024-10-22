from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from core.config import settings
import logging
from urllib.parse import urlparse
from utils.http_client import http_pool
from requests.models import Response
import json

logger = logging.getLogger(__name__)

class TwilioResponseAdapter:
    """Adapter to make urllib3 HTTPResponse look like requests Response"""
    def __init__(self, urllib3_response):
        self._response = urllib3_response
        self.status_code = urllib3_response.status
        self.content = urllib3_response.data
        self._cached_json = None

    @property
    def text(self):
        return self.content.decode('utf-8') if self.content else ''

    def json(self):
        if self._cached_json is None:
            self._cached_json = json.loads(self.text)
        return self._cached_json

    @property
    def ok(self):
        return 200 <= self.status_code < 300

class CustomTwilioHttpClient(TwilioHttpClient):
    def __init__(self):
        super().__init__()
        self.pool = http_pool.get_pool(
            host='api.twilio.com',
            maxsize=settings.TWILIO_MAX_CONNECTIONS
        )

    def request(self, method, url, params=None, data=None, headers=None, auth=None, timeout=None,
                allow_redirects=True):
        """
        Make an HTTP request with parameters provided.
        """
        try:
            logger.debug(f"Making Twilio request: {method} {url}")

            # Prepare auth header
            if auth:
                auth_string = f"{auth[0]}:{auth[1]}"
                import base64
                auth_header = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
                if headers is None:
                    headers = {}
                headers['Authorization'] = f'Basic {auth_header}'

            # Use the connection pool to make the request
            response = self.pool.request(
                method=method,
                url=url,
                fields=data,
                headers=headers,
                timeout=timeout,
                retries=False if not allow_redirects else None,
            )

            # Log response status
            logger.debug(f"Twilio response status: {response.status}")

            # Wrap the response in our adapter
            adapted_response = TwilioResponseAdapter(response)
            
            if not adapted_response.ok:
                logger.error(f"Twilio request failed with status {adapted_response.status_code}: {adapted_response.text}")

            return adapted_response

        except Exception as e:
            logger.error(f"Twilio request error: {str(e)}")
            raise

class MessagingService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        try:
            http_client = CustomTwilioHttpClient()
            self.client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
                http_client=http_client
            )
            self.twilio_number = settings.TWILIO_NUMBER
        except Exception as e:
            self.logger.error(f"Error initializing MessagingService: {str(e)}")
            raise

    def send_message(self, to_number: str, body_text: str):
        try:
            # Ensure the number has the whatsapp: prefix
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"

            from_number = f"whatsapp:{self.twilio_number}"

            self.logger.debug(f"Sending message - To: {to_number}, From: {from_number}, Body: {body_text}")

            # Create and send the message
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