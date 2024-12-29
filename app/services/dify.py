# app/services/dify.py

from dify_client import ChatClient
import structlog
import re
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from app.core.config import settings
from app.utils.redis_helpers import AsyncRedisLock, cache

logger = structlog.get_logger(__name__)

class DifyError(Exception):
    """Custom exception for Dify-related errors"""
    def __init__(self, message: str, error_code: str = "DIFY_ERROR"):
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

    async def _execute_with_retry(self, func, *args, max_retries=3, **kwargs):
        """Execute a function with retry logic"""
        last_error = None
        for attempt in range(max_retries):
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: func(*args, **kwargs)
                )
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    "dify_operation_retry",
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        raise last_error

    async def get_conversation_id(self, user: str) -> Optional[str]:
        """Get conversation ID for a user with caching and error handling"""
        try:
            formatted_user = await self.format_phone_number(user)
            cache_key = f"{self.cache_prefix}conv:{formatted_user}"

            # Check cache
            cached_id = await cache.get(cache_key)
            if cached_id:
                return cached_id

            # Use distributed lock
            async with AsyncRedisLock(f"dify_conv:{formatted_user}"):
                # Send initial message to create conversation
                response = await self._execute_with_retry(
                    self.chat_client.create_chat_message,
                    query="init",
                    user=formatted_user,
                    conversation_id=None,  # This will create a new conversation
                    inputs={},
                    response_mode="blocking"
                )

                if isinstance(response, dict):
                    conv_id = response.get("conversation_id")
                    if conv_id:
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
            raise DifyError(f"Failed to get conversation: {str(e)}")

    async def send_message(
        self,
        user: str,
        message: str,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send message to Dify service with improved error handling"""
        try:
            if not message:
                raise DifyError("Message cannot be empty", "INVALID_MESSAGE")

            formatted_user = await self.format_phone_number(user)

            # Create chat message with retry
            response = await self._execute_with_retry(
                self.chat_client.create_chat_message,
                query=message,
                user=formatted_user,
                conversation_id=conversation_id,
                inputs={},
                response_mode="blocking"
            )

            if not isinstance(response, dict):
                raise DifyError("Invalid response format from Dify")

            answer = response.get("answer")
            if not answer:
                raise DifyError("No response received from Dify")

            return {
                "message": answer,
                "conversation_id": response.get("conversation_id", conversation_id),
                "timestamp": datetime.utcnow().isoformat()
            }

        except DifyError:
            raise
        except Exception as e:
            logger.error(
                "send_message_failed",
                user=user,
                error=str(e),
                error_type=type(e).__name__
            )
            raise DifyError(f"Failed to process message: {str(e)}")

    async def format_phone_number(self, phone_number: str) -> str:
        """Format phone number for Dify chat"""
        try:
            # Remove whatsapp: prefix and whitespace
            phone_number = phone_number.replace("whatsapp:", "").strip()

            # Ensure it starts with +
            if not phone_number.startswith('+'):
                phone_number = f"+{phone_number}"

            # Basic validation - we'll make this more lenient
            if not re.match(r'^\+?\d{10,15}$', phone_number):
                raise DifyError("Invalid phone number format", "INVALID_PHONE")

            return phone_number

        except Exception as e:
            logger.error(
                "phone_formatting_failed",
                phone_number=phone_number,
                error=str(e)
            )
            raise DifyError(f"Failed to format phone number: {str(e)}")

    async def health_check(self) -> bool:
        """Check if Dify service is healthy"""
        try:
            # Try to send a test message
            await self._execute_with_retry(
                self.chat_client.create_chat_message,
                query="healthcheck",
                user="healthcheck",
                inputs={},
                response_mode="blocking"
            )
            return True
        except Exception as e:
            logger.error("dify_health_check_failed", error=str(e))
            return False