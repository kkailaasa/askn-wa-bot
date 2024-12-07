# app/services/twilio.py

from twilio.rest import Client
from twilio.request_validator import RequestValidator
from typing import Optional
import structlog
from app.core.config import settings
from app.services.load_balancer import LoadBalancer

logger = structlog.get_logger()

class TwilioClient:
    def __init__(self):
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        self.numbers = settings.TWILIO_NUMBERS
        self.load_balancer = LoadBalancer(self.numbers)

    async def send_message(self, to: str, body: str) -> Optional[dict]:
        try:
            from_number = await self.load_balancer.get_available_number()
            if not from_number:
                raise Exception("No available WhatsApp numbers")

            # Format numbers for WhatsApp
            to_number = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to
            from_number = f"whatsapp:{from_number}" if not from_number.startswith("whatsapp:") else from_number

            message = self.client.messages.create(
                from_=from_number,
                body=body,
                to=to_number
            )

            return {
                "sid": message.sid,
                "status": message.status,
                "from": message.from_
            }

        except Exception as e:
            logger.error("twilio_send_error", error=str(e), to=to)
            return None

    def verify_request(self, url: str, params: dict, signature: str) -> bool:
        """Verify Twilio request signature"""
        return self.validator.validate(
            url,
            params,
            signature
        )