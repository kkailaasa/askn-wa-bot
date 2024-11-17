# utils/redis_helpers.py

from utils.redis_pool import get_redis_client
from core.config import settings
from services.rate_limiter import RateLimiter
from typing import Tuple, Dict, Any, Optional, List, Union
from fastapi import Request
import logging
import json
import time
import asyncio
from datetime import datetime
from redis.exceptions import (
    RedisError,
    WatchError,
    ConnectionError,
    TimeoutError,
    LockError
)
from core.sequence_errors import (
    SequenceException,
    SequenceErrorCode,
    handle_sequence_error
)

logger = logging.getLogger(__name__)

redis_client = get_redis_client()
rate_limiter = RateLimiter(redis_client)

class RedisLock:
    """Enhanced distributed lock implementation"""
    def __init__(
        self,
        key: str,
        expire: int = settings.SEQUENCE.SEQUENCE_LOCK_TIMEOUT,
        retry_times: int = settings.REDIS_CONNECTION_RETRIES,
        retry_delay: float = settings.REDIS_RETRY_DELAY
    ):
        self.key = f"lock:{key}"
        self.expire = expire
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.acquired = False

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()

    async def acquire(self) -> bool:
        """Acquire lock with retry mechanism"""
        for attempt in range(self.retry_times):
            try:
                self.acquired = bool(
                    redis_client.set(
                        self.key,
                        str(time.time()),
                        nx=True,
                        ex=self.expire
                    )
                )
                if self.acquired:
                    return True
                if attempt < self.retry_times - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
            except RedisError as e:
                logger.error(f"Error acquiring lock: {str(e)}")
                if attempt == self.retry_times - 1:
                    raise SequenceException(
                        error_code=SequenceErrorCode.LOCK_ACQUISITION_FAILED,
                        message="Failed to acquire lock",
                        status_code=423
                    )
        return False

    async def release(self) -> bool:
        """Release the lock"""
        if self.acquired:
            try:
                result = bool(redis_client.delete(self.key))
                self.acquired = not result
                return result
            except RedisError as e:
                logger.error(f"Error releasing lock: {str(e)}")
                return False
        return True

class RedisTransaction:
    """Transaction manager for Redis operations"""
    def __init__(self, keys: List[str], retry_times: int = 3):
        self.keys = keys
        self.retry_times = retry_times
        self.pipeline = None

    async def __aenter__(self):
        self.pipeline = redis_client.pipeline()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.pipeline:
            self.pipeline.reset()

    async def execute(self, operation) -> Any:
        """Execute operation with optimistic locking"""
        for attempt in range(self.retry_times):
            try:
                self.pipeline.watch(*self.keys)
                result = await operation(self.pipeline)
                self.pipeline.execute()
                return result
            except WatchError:
                if attempt == self.retry_times - 1:
                    raise SequenceException(
                        error_code=SequenceErrorCode.CONCURRENT_MODIFICATION,
                        message="Concurrent modification detected",
                        status_code=409
                    )
                await asyncio.sleep(0.1 * (attempt + 1))
            except RedisError as e:
                raise handle_sequence_error(e, "redis_transaction")

async def is_rate_limited(request: Request, phone_number: str) -> bool:
    """
    Check if a phone number has exceeded its message rate limit
    
    Args:
        request: FastAPI request object
        phone_number: The phone number to check
        
    Returns:
        bool: True if rate limited, False otherwise
    """
    try:
        is_limited, _ = await rate_limiter.is_rate_limited(
            request=request,
            rate_limit_type="message",
            settings=settings
        )
        return is_limited
    except Exception as e:
        logger.error(f"Error checking rate limit: {str(e)}")
        return False

async def get_remaining_limit(request: Request, phone_number: str) -> Tuple[int, int]:
    """
    Get remaining messages allowed and time until reset
    """
    try:
        remaining, reset_time = rate_limiter.get_remaining_limit(
            request=request,
            rate_limit_type="message",
            settings=settings
        )
        return remaining, reset_time
    except Exception as e:
        logger.error(f"Error getting remaining limit: {str(e)}")
        return settings.MESSAGE_RATE_LIMIT, settings.MESSAGE_RATE_WINDOW

class CacheManager:
    """Enhanced cache management with serialization and error handling"""
    def __init__(self, prefix: str = "cache"):
        self.prefix = prefix

    def _get_key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def set(
        self,
        key: str,
        value: Any,
        expiry: int = settings.SEQUENCE.SEQUENCE_EXPIRY
    ) -> bool:
        """Set cache value with serialization"""
        try:
            serialized = (
                json.dumps(value)
                if not isinstance(value, (str, int, float, bool))
                else str(value)
            )
            return bool(
                redis_client.set(
                    self._get_key(key),
                    serialized,
                    ex=expiry
                )
            )
        except Exception as e:
            logger.error(f"Cache set error: {str(e)}")
            return False

    async def get(self, key: str, default: Any = None) -> Any:
        """Get cache value with deserialization"""
        try:
            value = redis_client.get(self._get_key(key))
            if value is None:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value.decode()
        except Exception as e:
            logger.error(f"Cache get error: {str(e)}")
            return default

    async def delete(self, key: str) -> bool:
        """Delete cache value"""
        try:
            return bool(redis_client.delete(self._get_key(key)))
        except Exception as e:
            logger.error(f"Cache delete error: {str(e)}")
            return False

class QueueManager:
    """Queue management with error handling and monitoring"""
    def __init__(self, queue_name: str):
        self.queue_name = f"queue:{queue_name}"
        self.processing_key = f"processing:{queue_name}"

    async def enqueue(self, item: Any) -> bool:
        """Add item to queue"""
        try:
            serialized = json.dumps({
                "data": item,
                "timestamp": datetime.utcnow().isoformat(),
                "attempts": 0
            })
            return bool(redis_client.rpush(self.queue_name, serialized))
        except Exception as e:
            logger.error(f"Queue enqueue error: {str(e)}")
            return False

    async def dequeue(self) -> Optional[Dict[str, Any]]:
        """Get and remove item from queue"""
        try:
            data = redis_client.lpop(self.queue_name)
            if data:
                item = json.loads(data)
                # Track processing
                redis_client.hset(
                    self.processing_key,
                    item['timestamp'],
                    data
                )
                return item['data']
            return None
        except Exception as e:
            logger.error(f"Queue dequeue error: {str(e)}")
            return None

async def cleanup_expired_keys(pattern: str) -> int:
    """
    Clean up expired keys matching pattern
    Returns number of keys cleaned
    """
    try:
        cleaned = 0
        for key in redis_client.scan_iter(f"{pattern}:*"):
            if redis_client.ttl(key) <= 0:
                redis_client.delete(key)
                cleaned += 1
        return cleaned
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        return 0

# Initialize managers
cache = CacheManager()

__all__ = [
    'redis_client',
    'rate_limiter',
    'RedisLock',
    'RedisTransaction',
    'is_rate_limited',
    'get_remaining_limit',
    'cache',
    'QueueManager',
    'cleanup_expired_keys'
]