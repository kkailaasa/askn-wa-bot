# app/services/twilio.py

from twilio.rest import Client
from twilio.request_validator import RequestValidator
from typing import Optional, Dict, Any
import structlog
from app.core.config import settings

logger = structlog.get_logger()

class TwilioClient:
    def __init__(self):
        """Initialize Twilio client with settings"""
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        self.numbers = settings.get_twilio_numbers()

        if not self.numbers:
            logger.error("no_twilio_numbers_configured")
            raise ValueError("No Twilio numbers configured")

        logger.info(
            "twilio_client_initialized",
            number_count=len(self.numbers)
        )

    async def send_message(self, to: str, body: str, from_number: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Send WhatsApp message using Twilio"""
        try:
            # Format numbers for WhatsApp
            to_number = f"whatsapp:{to}" if not to.startswith("whatsapp:") else to

            # Use provided number or first available number
            from_number = from_number or self.numbers[0]
            from_wa = f"whatsapp:{from_number}" if not from_number.startswith("whatsapp:") else from_number

            message = self.client.messages.create(
                from_=from_wa,
                body=body,
                to=to_number
            )

            logger.info(
                "message_sent",
                to=to_number,
                from_number=from_wa,
                message_sid=message.sid
            )

            return {
                "sid": message.sid,
                "status": message.status,
                "from": message.from_
            }

        except Exception as e:
            logger.error(
                "twilio_send_error",
                error=str(e),
                to=to,
                from_number=from_number
            )
            return None

    def verify_request(self, url: str, params: dict, signature: str) -> bool:
        """Verify Twilio request signature"""
        try:
            return self.validator.validate(
                url,
                params,
                signature
            )
        except Exception as e:
            logger.error(
                "signature_verification_error",
                error=str(e)
            )
            return False

    async def health_check(self) -> bool:
        """Check if Twilio service is healthy"""
        try:
            # Try to fetch account info as a basic health check
            self.client.api.accounts(settings.TWILIO_ACCOUNT_SID).fetch()
            return True
        except Exception as e:
            logger.error("twilio_health_check_failed", error=str(e))
            return False