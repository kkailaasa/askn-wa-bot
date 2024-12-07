# app/utils/redis_helpers.py

import aioredis
import json
from typing import Optional, Any
from datetime import datetime
from app.core.config import settings
import structlog

logger = structlog.get_logger()

# Initialize Redis connection
redis = aioredis.from_url(
    f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
    password=settings.REDIS_PASSWORD,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    retry_on_timeout=True
)

class AsyncRedisLock:
    """Distributed lock using Redis"""
    def __init__(self, key: str, expire: int = 60):
        self.key = f"lock:{key}"
        self.expire = expire

    async def __aenter__(self):
        while True:
            if await redis.set(self.key, 1, nx=True, ex=self.expire):
                return self
            await asyncio.sleep(0.1)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await redis.delete(self.key)

class RedisCache:
    """Redis cache wrapper with type hints and error handling"""

    async def get(self, key: str) -> Optional[Any]:
        try:
            data = await redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error("redis_get_error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, expiry: int = 3600) -> bool:
        try:
            await redis.set(
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
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, window)
            result = await pipe.execute()
            return result[0]
        except Exception as e:
            logger.error("redis_increment_error", key=key, error=str(e))
            return 0

class MessageCounter:
    """Track message counts per number in Redis"""

    def __init__(self, window: int = 60):
        self.window = window

    async def increment(self, number: str) -> int:
        """Increment message count for number"""
        key = f"msg_count:{number}:{int(datetime.now().timestamp() / self.window)}"
        return await cache.increment(key, self.window)

    async def get_count(self, number: str) -> int:
        """Get current message count for number"""
        key = f"msg_count:{number}:{int(datetime.now().timestamp() / self.window)}"
        count = await cache.get(key)
        return count if count else 0

# Initialize global instances
cache = RedisCache()
message_counter = MessageCounter()