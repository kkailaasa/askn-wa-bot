# app/services/twilio.py

from twilio.rest import Client
from typing import Optional, Dict, Any
import structlog
from app.core.config import settings
import asyncio
import re

logger = structlog.get_logger()

class TwilioClient:
    def __init__(self):
        """Initialize Twilio client with settings"""
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.numbers = settings.get_twilio_numbers()

        if not self.numbers:
            logger.error("no_twilio_numbers_configured")
            raise ValueError("No Twilio numbers configured")

        logger.info(
            "twilio_client_initialized",
            number_count=len(self.numbers)
        )

    def _format_whatsapp_number(self, number: str) -> str:
        """Format phone number for WhatsApp"""
        # Remove any existing whatsapp: prefix and spaces
        number = number.replace("whatsapp:", "").strip()

        # Remove any non-digit characters except +
        number = re.sub(r'[^\d+]', '', number)

        # Ensure number starts with +
        if not number.startswith('+'):
            number = f"+{number}"

        # Add whatsapp: prefix
        return f"whatsapp:{number}"

    async def send_message(
        self,
        to: str,
        body: str,
        from_number: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Send WhatsApp message using Twilio"""
        try:
            # Format numbers for WhatsApp
            to_number = self._format_whatsapp_number(to)

            # Use provided number or first available number
            from_number = from_number or self.numbers[0]
            from_wa = self._format_whatsapp_number(from_number)

            # Run Twilio API call in thread pool
            loop = asyncio.get_running_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    from_=from_wa,
                    body=body,
                    to=to_number
                )
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

    async def health_check(self) -> bool:
        """Check if Twilio service is healthy"""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.api.accounts(settings.TWILIO_ACCOUNT_SID).fetch()
            )
            return True
        except Exception as e:
            logger.error("twilio_health_check_failed", error=str(e))
            return False