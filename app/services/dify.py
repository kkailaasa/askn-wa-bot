# app/services/dify.py

import aiohttp
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
        """Initialize Dify service with API configuration"""
        self.api_base = settings.DIFY_URL.rstrip('/')
        self.api_key = settings.DIFY_KEY
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        self.cache_prefix = "dify_chat:"
        
        logger.info(
            "dify_service_initialized",
            dify_url=settings.DIFY_URL
        )

    async def get_conversation_id(self, user: str) -> Optional[str]:
        """Get existing conversation ID for user from Dify"""
        try:
            formatted_user = await self.format_phone_number(user)
            cache_key = f"{self.cache_prefix}conv:{formatted_user}"

            # Check cache first
            cached_id = await cache.get(cache_key)
            if cached_id:
                return cached_id

            # Make API request to get conversations
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_base}/conversations",
                    headers=self.headers,
                    params={"user": formatted_user, "limit": 1}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        conversations = data.get("data", [])
                        if conversations:
                            conv_id = conversations[0].get("id")
                            if conv_id:
                                await cache.set(cache_key, conv_id, expiry=3600)
                                return conv_id
            
            # No existing conversation found
            return None

        except Exception as e:
            logger.error(
                "get_conversation_failed",
                user=user,
                error=str(e)
            )
            return None

    async def send_message(
        self,
        user: str,
        message: str,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send message to Dify API"""
        try:
            if not message:
                raise DifyError("Message cannot be empty")

            formatted_user = await self.format_phone_number(user)

            # Prepare request payload
            payload = {
                "query": message,
                "user": formatted_user,
                "response_mode": "blocking",
                "conversation_id": conversation_id or "",
                "inputs": {}
            }

            # Send request to Dify API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/chat-messages",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        raise DifyError(
                            error_data.get("message", "Unknown error"),
                            error_data.get("code", "UNKNOWN_ERROR")
                        )

                    data = await response.json()
                    
                    # Extract relevant information from response
                    return {
                        "message": data.get("answer", ""),
                        "conversation_id": data.get("conversation_id", conversation_id),
                        "message_id": data.get("message_id", ""),
                        "timestamp": datetime.utcnow().isoformat()
                    }

        except DifyError:
            raise
        except Exception as e:
            logger.error(
                "send_message_failed",
                user=user,
                error=str(e)
            )
            raise DifyError(f"Failed to process message: {str(e)}")

    async def format_phone_number(self, phone_number: str) -> str:
        """Format phone number for Dify API"""
        try:
            # Remove whatsapp: prefix and clean up
            phone_number = phone_number.replace("whatsapp:", "").strip()
            phone_number = re.sub(r'[^\d+]', '', phone_number)

            # Ensure it starts with +
            if not phone_number.startswith('+'):
                phone_number = f"+{phone_number}"

            return phone_number

        except Exception as e:
            logger.error(
                "phone_formatting_failed",
                phone_number=phone_number,
                error=str(e)
            )
            raise DifyError(f"Failed to format phone number: {str(e)}")

    async def health_check(self) -> bool:
        """Check Dify API health by checking parameters endpoint"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_base}/parameters",
                    headers=self.headers,
                    params={"user": "health_check"}
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error("dify_health_check_failed", error=str(e))
            return False