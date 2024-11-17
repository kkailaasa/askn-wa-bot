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
            try:
                self._cached_json = json.loads(self.text)
            except json.JSONDecodeError:
                self._cached_json = {}
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
        try:
            logger.debug(f"Making Twilio request: {method} {url}")
            logger.debug(f"Request data: {data}")
            logger.debug(f"Request headers: {headers}")

            if auth:
                auth_string = f"{auth[0]}:{auth[1]}"
                import base64
                auth_header = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
                if headers is None:
                    headers = {}
                headers['Authorization'] = f'Basic {auth_header}'

            response = self.pool.request(
                method=method,
                url=url,
                fields=data,
                headers=headers,
                timeout=timeout,
                retries=False if not allow_redirects else None,
            )

            logger.debug(f"Twilio response status: {response.status}")
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
            # Don't use the custom HTTP client for now to debug the issue
            self.client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN
            )
            self.twilio_number = settings.TWILIO_NUMBER.strip()
            if not self.twilio_number:
                raise ValueError("TWILIO_NUMBER not configured")

            self.logger.debug(f"MessagingService initialized with number: {self.twilio_number}")
        except Exception as e:
            self.logger.error(f"Error initializing MessagingService: {str(e)}")
            raise

    def format_phone_number(self, phone_number: str, add_whatsapp: bool = True) -> str:
        """Format phone number with better validation."""
        if not phone_number:
            raise ValueError("Phone number cannot be empty")

        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone_number.strip())

        # Ensure it starts with + if it doesn't
        if not cleaned.startswith('+'):
            cleaned = f"+{cleaned}"

        # Validate length
        if len(re.sub(r'[^\d]', '', cleaned)) < 10:
            raise ValueError("Phone number too short")

        if add_whatsapp:
            return f"whatsapp:{cleaned}"
        return cleaned

    def validate_phone_number(self, phone_number: str) -> bool:
        """Basic validation for phone numbers."""
        cleaned = phone_number.replace("whatsapp:", "").replace("+", "").strip()
        valid = (
            cleaned.isdigit() and  # Only contains digits
            len(cleaned) >= 10 and  # At least 10 digits
            len(cleaned) <= 15      # No more than 15 digits
        )
        self.logger.debug(f"Phone number validation - Original: {phone_number}, Cleaned: {cleaned}, Valid: {valid}")
        return valid

    def send_message(self, to_number: str, body_text: str):
        try:
            self.logger.debug(f"Sending message - Raw to_number: {to_number}")

            if not to_number or not body_text:
                raise ValueError("Both 'to_number' and 'body_text' are required")

            # Format the 'to' number with WhatsApp prefix
            to_formatted = self.format_phone_number(to_number, add_whatsapp=True)
            # Format the 'from' number with WhatsApp prefix
            from_formatted = self.format_phone_number(self.twilio_number, add_whatsapp=True)

            self.logger.debug(f"Formatted numbers - To: {to_formatted}, From: {from_formatted}")

            if not self.validate_phone_number(to_formatted):
                raise ValueError(f"Invalid 'to' phone number format: {to_formatted}")

            if not self.validate_phone_number(from_formatted):
                raise ValueError(f"Invalid 'from' phone number format: {from_formatted}")

            # Create the message - Note the parameter names!
            self.logger.debug("Attempting to send message with Twilio client")
            message = self.client.messages.create(
                to=to_formatted,    # Use 'to', not 'to_'
                from_=from_formatted,  # Note the underscore in 'from_'
                body=body_text
            )

            self.logger.info(f"Message sent successfully - SID: {message.sid}")
            self.logger.debug(f"Complete message object: {message}")

            return message.sid

        except ValueError as ve:
            self.logger.error(f"Validation error: {str(ve)}")
            raise
        except Exception as e:
            self.logger.error(f"Error sending message: {str(e)}", exc_info=True)
            raise