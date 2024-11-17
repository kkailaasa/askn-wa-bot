from typing import Optional, Dict, Any, Tuple
from dify_client import ChatClient
from core.config import settings
import logging
import structlog
from urllib.parse import urlparse
from utils.http_client import http_pool
from core.sequence_errors import SequenceException, SequenceErrorCode
import asyncio
import re
from utils.logging_utils import log_error
from datetime import datetime
import json
from utils.redis_helpers import RedisLock, cache
from fastapi import HTTPException

logger = structlog.get_logger(__name__)

class ChatService:
    def __init__(self):
        """Initialize ChatService with enhanced error handling and monitoring"""
        try:
            self.chat_client = ChatClient(settings.DIFY_KEY)
            self.chat_client.base_url = settings.DIFY_URL

            # Setup connection pool for Dify
            dify_url = urlparse(settings.DIFY_URL)
            self.dify_pool = http_pool.get_pool(
                host=dify_url.netloc,
                maxsize=settings.DIFY_MAX_CONNECTIONS,
                timeout=settings.DIFY_TIMEOUT,
                retries=3
            )

            # Setup cache prefix for this service
            self.cache_prefix = "dify_chat:"

            logger.info(
                "chat_service_initialized",
                dify_url=settings.DIFY_URL,
                max_connections=settings.DIFY_MAX_CONNECTIONS
            )
        except Exception as e:
            logger.error(
                "chat_service_initialization_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        max_retries: int = 3,
        **kwargs
    ) -> Any:
        """Make HTTP request to Dify API with retries and error handling"""
        last_error = None

        for attempt in range(max_retries):
            try:
                url = f"{self.chat_client.base_url}{endpoint}"

                # Add request tracking headers
                headers = {
                    **self.chat_client.headers,
                    "X-Request-Time": datetime.utcnow().isoformat(),
                    "X-Retry-Count": str(attempt)
                }

                if kwargs.get('headers'):
                    headers.update(kwargs['headers'])
                kwargs['headers'] = headers

                # Make request with timeout
                async with asyncio.timeout(settings.DIFY_TIMEOUT):
                    response = self.dify_pool.request(method, url, **kwargs)

                    if response.status >= 400:
                        error_data = json.loads(response.data.decode('utf-8'))
                        raise SequenceException(
                            error_code=SequenceErrorCode.DIFY_ERROR,
                            message=error_data.get('message', 'Dify API error'),
                            status_code=response.status
                        )

                    return response

            except asyncio.TimeoutError:
                last_error = SequenceException(
                    error_code=SequenceErrorCode.TIMEOUT,
                    message="Dify API request timed out",
                    status_code=504
                )
            except Exception as e:
                last_error = e

                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                break

        logger.error(
            "dify_request_failed",
            method=method,
            endpoint=endpoint,
            error=str(last_error),
            attempts=attempt + 1
        )
        raise last_error

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
            return ""

        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)

        # Validate format
        if not re.match(r'^\+?\d{10,15}$', cleaned):
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_PHONE,
                message="Invalid phone number format"
            )

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
            if not re.match(r'^\+\d{10,15}$', phone_number):
                raise SequenceException(
                    error_code=SequenceErrorCode.INVALID_PHONE,
                    message="Invalid phone number format after formatting"
                )

            logger.debug("phone_number_formatted", result=phone_number)
            return phone_number

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
            async with RedisLock(f"dify_conv:{formatted_user}"):
                response = await self._make_request(
                    'GET',
                    f'/conversations?user={formatted_user}'
                )

                response_data = json.loads(response.data.decode('utf-8'))
                logger.debug("conversations_response", response=response_data)

                if "data" in response_data:
                    conversations = response_data.get("data", [])
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
            await log_error(
                error_type="DifyError",
                error_message=str(e),
                phone_number=user,
                metadata={"operation": "get_conversation_id"}
            )
            return None

    async def create_chat_message(
        self,
        phone_number: str,
        message: str,
        conversation_id: Optional[str] = None,
        auth_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a chat message with comprehensive error handling and validation"""
        try:
            # Input validation
            if not message:
                raise SequenceException(
                    error_code=SequenceErrorCode.INVALID_DATA,
                    message="Message cannot be empty"
                )

            if len(message) > 4096:
                raise SequenceException(
                    error_code=SequenceErrorCode.INVALID_DATA,
                    message="Message exceeds maximum length"
                )

            # Sanitize inputs
            sanitized_message = self._sanitize_message(message)
            sanitized_phone = self._sanitize_phone(phone_number)
            formatted_phone = await self.format_phone_number(sanitized_phone)

            # Prepare request payload
            payload = {
                "inputs": auth_context or {},
                "query": sanitized_message,
                "user": formatted_phone,
                "conversation_id": conversation_id,
                "response_mode": "blocking"
            }

            logger.debug(
                "creating_chat_message",
                phone=formatted_phone,
                conversation_id=conversation_id,
                message_length=len(sanitized_message)
            )

            # Make request with retry logic
            response = await self._make_request(
                'POST',
                '/chat/completions',
                json=payload
            )

            response_data = json.loads(response.data.decode('utf-8'))
            logger.debug("chat_response_received", response=response_data)

            # Handle auth verification needs
            if response_data.get("needs_auth_verification"):
                required_operation = response_data.get("required_operation")
                if not required_operation:
                    raise SequenceException(
                        error_code=SequenceErrorCode.INVALID_DATA,
                        message="Missing required operation in auth verification request"
                    )

                return {
                    "needs_auth_verification": True,
                    "required_operation": required_operation,
                    "operation_data": response_data.get("operation_data", {}),
                    "message": response_data.get("message", "Additional verification needed")
                }

            # Return normal response
            return {
                "message": response_data.get("answer", "I'm sorry, I couldn't process your message."),
                "conversation_id": response_data.get("conversation_id"),
                "timestamp": datetime.utcnow().isoformat(),
                "success": True
            }

        except SequenceException:
            raise
        except Exception as e:
            logger.error(
                "chat_message_error",
                phone_number=phone_number,
                conversation_id=conversation_id,
                error=str(e),
                error_type=type(e).__name__
            )
            await log_error(
                error_type="DifyError",
                error_message=str(e),
                phone_number=phone_number,
                metadata={
                    "operation": "create_chat_message",
                    "conversation_id": conversation_id
                }
            )
            raise SequenceException(
                error_code=SequenceErrorCode.DIFY_ERROR,
                message="Failed to process chat message",
                status_code=500
            )

    async def health_check(self) -> bool:
        """Check Dify service health"""
        try:
            response = await self._make_request(
                'GET',
                '/health',
                max_retries=1
            )
            return response.status == 200
        except Exception as e:
            logger.error("dify_health_check_failed", error=str(e))
            return False