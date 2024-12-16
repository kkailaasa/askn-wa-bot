# app/services/dify.py

from dify_client import ChatClient
import structlog
import re
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from app.core.config import settings
from app.utils.redis_helpers import AsyncRedisLock, cache

logger = structlog.get_logger(__name__)

class DifyError(Exception):
    def __init__(self, message: str, error_code: str):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class DifyService:
    def __init__(self):
        try:
            self.chat_client = ChatClient(settings.DIFY_KEY)
            self.chat_client.base_url = settings.DIFY_URL
            self.cache_prefix = "dify_chat:"

            logger.info(
                "dify_service_initialized",
                dify_url=settings.DIFY_URL,
                max_connections=settings.DIFY_MAX_CONNECTIONS
            )
        except Exception as e:
            logger.error(
                "dify_service_initialization_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def health_check(self) -> bool:
        """Check if Dify service is healthy by trying to list conversations"""
        try:
            # Try to get conversations as a basic health check
            await self.chat_client.get_conversations(user="healthcheck")
            return True
        except Exception as e:
            logger.error("dify_health_check_failed", error=str(e))
            return False

    def _sanitize_message(self, message: str) -> str:
        """Sanitize message content with enhanced validation"""
        if not message:
            return ""

        # Remove control characters and Unicode
        sanitized = "".join(char for char in message if char.isprintable())

        # Additional security checks
        sanitized = re.sub(r'[^\w\s\-.,?!@#$%^&*()[\]{}|\\/\'\":;~`<>+=]', '', sanitized)

        # Enforce maximum length
        max_length = 4096
        if len(sanitized) > max_length:
            logger.warning(
                "message_truncated",
                original_length=len(message),
                truncated_length=max_length
            )
            return sanitized[:max_length]

        return sanitized

    def _sanitize_phone(self, phone: str) -> str:
        """Sanitize phone number with enhanced validation"""
        if not phone:
            raise DifyError("Phone number cannot be empty", "INVALID_PHONE")

        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)

        # Validate format
        if not re.match(r'^\+?\d{10,15}$', cleaned):
            raise DifyError("Invalid phone number format", "INVALID_PHONE")

        return cleaned

    async def format_phone_number(self, phone_number: str) -> str:
        """Format phone number for Dify chat with validation"""
        logger.debug("formatting_phone_number", phone_number=phone_number)

        try:
            # Remove whatsapp: prefix and whitespace
            phone_number = phone_number.replace("whatsapp:", "").strip()

            # Ensure it starts with +
            if not phone_number.startswith('+'):
                phone_number = f"+{phone_number}"

            # Validate final format
            sanitized_phone = self._sanitize_phone(phone_number)

            logger.debug("phone_number_formatted", result=sanitized_phone)
            return sanitized_phone

        except Exception as e:
            logger.error(
                "phone_formatting_failed",
                phone_number=phone_number,
                error=str(e)
            )
            raise

    async def get_conversation_id(self, user: str) -> Optional[str]:
        """Get conversation ID for a user with caching and error handling"""
        cache_key = f"{self.cache_prefix}conv:{user}"

        try:
            # Check cache first
            cached_id = await cache.get(cache_key)
            if cached_id:
                return cached_id

            logger.debug("getting_conversations", user=user)
            formatted_user = await self.format_phone_number(user)

            # Use distributed lock to prevent concurrent requests
            async with AsyncRedisLock(f"dify_conv:{formatted_user}"):
                conversations = await self.chat_client.get_conversations(user=formatted_user)

                if conversations:
                    conv_id = conversations[0].get("id")
                    # Cache the result
                    await cache.set(cache_key, conv_id, expiry=3600)
                    return conv_id

            return None

        except Exception as e:
            logger.error(
                "get_conversation_failed",
                user=user,
                error=str(e),
                error_type=type(e).__name__
            )
            return None

    async def send_message(
        self,
        user: str,
        message: str,
        conversation_id: Optional[str] = None,
        auth_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send message to Dify service"""
        try:
            # Input validation and sanitization
            if not message:
                raise DifyError("Message cannot be empty", "INVALID_MESSAGE")

            sanitized_message = self._sanitize_message(message)
            formatted_phone = await self.format_phone_number(user)

            # Prepare request payload
            response = await self.chat_client.create_chat_message(
                query=sanitized_message,
                user=formatted_phone,
                conversation_id=conversation_id,
                inputs=auth_context or {},
                response_mode="blocking"
            )

            # Handle auth verification needs
            if response.get("needs_auth_verification"):
                return {
                    "needs_auth_verification": True,
                    "required_operation": response.get("required_operation"),
                    "operation_data": response.get("operation_data", {}),
                    "message": response.get("message", "Additional verification needed")
                }

            return {
                "message": response.get("answer", "I couldn't process your message."),
                "conversation_id": response.get("conversation_id"),
                "timestamp": datetime.utcnow().isoformat(),
                "success": True
            }

        except DifyError as e:
            logger.error("dify_validation_error", error=str(e), code=e.error_code)
            raise HTTPException(status_code=400, detail={"message": str(e), "code": e.error_code})
        except Exception as e:
            logger.error(
                "send_message_failed",
                user=user,
                error=str(e),
                error_type=type(e).__name__
            )
            raise HTTPException(status_code=500, detail="Failed to process message")