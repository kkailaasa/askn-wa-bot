from twilio.rest import Client
from core.config import settings
import logging

logger = logging.getLogger(__name__)

class MessagingService:
    def __init__(self):
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.twilio_number = settings.TWILIO_NUMBER

    def send_message(self, to_number: str, body_text: str):
        try:
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"

            message = self.client.messages.create(
                from_=f"whatsapp:{self.twilio_number}",
                body=body_text,
                to=to_number
            )
            logger.info(f"Message sent to {to_number}: {message.body}")
        except Exception as e:
            logger.error(f"Error sending message to {to_number}: {e}")
            raise e