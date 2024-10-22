from twilio.rest import Client
from core.config import settings
import logging

logger = logging.getLogger(__name__)

class MessagingService:
    def __init__(self):
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
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