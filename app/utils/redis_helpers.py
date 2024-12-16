# app/utils/redis_helpers.py

import redis.asyncio as redis
import json
from typing import Optional, Any
from datetime import datetime
import asyncio
from app.core.config import settings
import structlog

logger = structlog.get_logger()

# Initialize Redis connection
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    retry_on_timeout=True,
    decode_responses=True
)

class AsyncRedisLock:
    """Distributed lock using Redis"""
    def __init__(self, key: str, expire: int = 60):
        self.key = f"lock:{key}"
        self.expire = expire
        self._lock = None

    async def __aenter__(self):
        while True:
            locked = await redis_client.set(
                self.key,
                "1",
                ex=self.expire,
                nx=True
            )
            if locked:
                break
            await asyncio.sleep(0.1)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await redis_client.delete(self.key)

class RedisCache:
    """Redis cache wrapper with type hints and error handling"""

    async def get(self, key: str) -> Optional[Any]:
        try:
            data = await redis_client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error("redis_get_error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, expiry: int = 3600) -> bool:
        try:
            await redis_client.set(
                key,
                json.dumps(value),
                ex=expiry
            )
            return True
        except Exception as e:
            logger.error("redis_set_error", key=key, error=str(e))
            return False

    async def increment(self, key: str, window: int = 60) -> int:
        """Increment counter and expire after window"""
        try:
            pipe = redis_client.pipeline()
            await pipe.incr(key)
            await pipe.expire(key, window)
            result = await pipe.execute()
            return result[0]
        except Exception as e:
            logger.error("redis_increment_error", key=key, error=str(e))
            return 0

    async def ping(self) -> bool:
        """Check Redis connection"""
        try:
            return await redis_client.ping()
        except Exception as e:
            logger.error("redis_ping_error", error=str(e))
            return False

    async def close(self) -> None:
        """Close Redis connection"""
        try:
            await redis_client.close()
        except Exception as e:
            logger.error("redis_close_error", error=str(e))

class MessageCounter:
    """Track message counts per number in Redis"""

    def __init__(self, window: int = 60):
        self.window = window
        self.cache = RedisCache()

    async def increment(self, number: str) -> int:
        """Increment message count for number"""
        key = f"msg_count:{number}:{int(datetime.now().timestamp() / self.window)}"
        return await self.cache.increment(key, self.window)

    async def get_count(self, number: str) -> int:
        """Get current message count for number"""
        key = f"msg_count:{number}:{int(datetime.now().timestamp() / self.window)}"
        count = await self.cache.get(key)
        return count if count else 0

# Initialize global instances
cache = RedisCache()
message_counter = MessageCounter()