# utils/redis_helpers.py

import redis.asyncio as redis_async
from typing import Optional, Any, Dict, List, Union, Tuple
import json
import structlog
from datetime import datetime
import asyncio
from core.config import settings
from core.sequence_errors import SequenceException, SequenceErrorCode
from fastapi import Request

logger = structlog.get_logger(__name__)

class AsyncRedisHelper:
    """Singleton Redis connection manager"""
    _instance = None
    _redis: Optional[redis_async.Redis] = None
    _pool: Optional[redis_async.ConnectionPool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AsyncRedisHelper, cls).__new__(cls)
        return cls._instance

    async def init_pool(self) -> redis_async.ConnectionPool:
        """Initialize connection pool"""
        if self._pool is None:
            self._pool = redis_async.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                retry_on_timeout=True,
                health_check_interval=30
            )
        return self._pool

    async def init_redis(self) -> redis_async.Redis:
        """Initialize Redis connection"""
        if self._redis is None:
            pool = await self.init_pool()
            self._redis = redis_async.Redis(
                connection_pool=pool,
                health_check_interval=30,
                retry_on_timeout=True
            )
        return self._redis

    async def get_redis(self) -> redis_async.Redis:
        """Get Redis client with automatic retry"""
        if self._redis is None:
            self._redis = await self.init_redis()

        try:
            # Test connection
            await self._redis.ping()
            return self._redis
        except (redis_async.ConnectionError, redis_async.TimeoutError) as e:
            logger.warning("redis_connection_failed", error=str(e))
            # Close and retry
            await self.close()
            self._redis = await self.init_redis()
            return self._redis

    async def close(self):
        """Close Redis connection and pool"""
        if self._redis:
            await self._redis.close()
            self._redis = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis health status"""
        try:
            redis = await self.get_redis()
            start_time = datetime.utcnow()
            await redis.ping()
            response_time = (datetime.utcnow() - start_time).total_seconds()

            info = await redis.info()
            return {
                "status": "healthy",
                "response_time": response_time,
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory_human"),
                "version": info.get("redis_version"),
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

class AsyncRedisLock:
    """Distributed lock implementation"""
    def __init__(
        self,
        key: str,
        expire: int = 30,
        retry_delay: float = 0.1,
        max_retries: int = 3,
        redis_helper: Optional[AsyncRedisHelper] = None
    ):
        self.key = f"lock:{key}"
        self.expire = expire
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.redis_helper = redis_helper or AsyncRedisHelper()
        self.acquired = False
        self._owner = f"{datetime.utcnow().isoformat()}-{id(self)}"

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()

    async def acquire(self) -> bool:
        """Acquire lock with retry"""
        for attempt in range(self.max_retries):
            try:
                redis = await self.redis_helper.get_redis()
                self.acquired = await redis.set(
                    self.key,
                    self._owner,
                    ex=self.expire,
                    nx=True
                )
                if self.acquired:
                    return True
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
            except Exception as e:
                logger.error("lock_acquisition_failed", key=self.key, error=str(e))
                if attempt == self.max_retries - 1:
                    raise SequenceException(
                        error_code=SequenceErrorCode.LOCK_ACQUISITION_FAILED,
                        message="Failed to acquire lock",
                        status_code=423
                    )
        return False

    async def release(self) -> bool:
        """Release lock if owned by us"""
        if self.acquired:
            try:
                redis = await self.redis_helper.get_redis()
                # Only delete if we still own the lock
                current_owner = await redis.get(self.key)
                if current_owner == self._owner:
                    self.acquired = not await redis.delete(self.key)
                    return not self.acquired
            except Exception as e:
                logger.error("lock_release_failed", key=self.key, error=str(e))
        return True

class AsyncCache:
    """Enhanced caching implementation"""
    def __init__(
        self,
        redis_helper: Optional[AsyncRedisHelper] = None,
        prefix: str = "cache:"
    ):
        self.redis_helper = redis_helper or AsyncRedisHelper()
        self.prefix = prefix

    def _get_key(self, key: str) -> str:
        """Generate prefixed key"""
        return f"{self.prefix}{key}"

    async def set(
        self,
        key: str,
        value: Any,
        expiry: int = 3600,
        nx: bool = False
    ) -> bool:
        """Set cache value with options"""
        try:
            redis = await self.redis_helper.get_redis()
            serialized = (
                json.dumps(value)
                if not isinstance(value, (str, int, float, bool))
                else str(value)
            )
            return await redis.set(
                self._get_key(key),
                serialized,
                ex=expiry,
                nx=nx
            )
        except Exception as e:
            logger.error("cache_set_failed", key=key, error=str(e))
            return False

    async def get(self, key: str, default: Any = None) -> Any:
        """Get cache value"""
        try:
            redis = await self.redis_helper.get_redis()
            value = await redis.get(self._get_key(key))
            if value is None:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.error("cache_get_failed", key=key, error=str(e))
            return default

    async def delete(self, key: str) -> bool:
        """Delete cache value"""
        try:
            redis = await self.redis_helper.get_redis()
            return bool(await redis.delete(self._get_key(key)))
        except Exception as e:
            logger.error("cache_delete_failed", key=key, error=str(e))
            return False

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment counter"""
        try:
            redis = await self.redis_helper.get_redis()
            return await redis.incrby(self._get_key(key), amount)
        except Exception as e:
            logger.error("cache_increment_failed", key=key, error=str(e))
            return None

    async def expire(self, key: str, seconds: int) -> bool:
        """Set key expiration"""
        try:
            redis = await self.redis_helper.get_redis()
            return await redis.expire(self._get_key(key), seconds)
        except Exception as e:
            logger.error("cache_expire_failed", key=key, error=str(e))
            return False

class RateLimiter:
    """Rate limiting implementation"""
    def __init__(
        self,
        redis_helper: Optional[AsyncRedisHelper] = None,
        prefix: str = "ratelimit:"
    ):
        self.redis_helper = redis_helper or AsyncRedisHelper()
        self.prefix = prefix

    def _get_key(self, identifier: str, rate_limit_type: str) -> str:
        """Generate rate limit key"""
        return f"{self.prefix}{rate_limit_type}:{identifier}"

    async def is_rate_limited(
        self,
        request: Request,
        rate_limit_type: str,
        settings: Any
    ) -> Tuple[bool, Optional[int]]:
        """Check if request is rate limited"""
        try:
            config = settings.rate_limit_config.get(rate_limit_type)
            if not config:
                logger.warning(f"No rate limit configuration for {rate_limit_type}")
                return False, None

            redis = await self.redis_helper.get_redis()
            key = self._get_key(request.client.host, rate_limit_type)
            current_time = datetime.utcnow().timestamp()

            # Clean up old entries and count current ones
            pipe = redis.pipeline()
            pipe.zremrangebyscore(
                key,
                0,
                current_time - config['period']
            )
            pipe.zcard(key)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.expire(key, config['period'])
            
            _, count, _, _ = await pipe.execute()

            is_limited = count > config['limit']
            retry_after = config['period'] if is_limited else None

            if is_limited:
                logger.warning(
                    "rate_limit_exceeded",
                    type=rate_limit_type,
                    client=request.client.host,
                    count=count,
                    limit=config['limit']
                )

            return is_limited, retry_after

        except Exception as e:
            logger.error(
                "rate_limit_check_failed",
                type=rate_limit_type,
                error=str(e)
            )
            return False, None

async def cleanup_expired_keys(pattern: str) -> int:
    """Clean up expired keys matching pattern"""
    try:
        redis = await redis_helper.get_redis()
        cleaned = 0
        async for key in redis.scan_iter(f"{pattern}*"):
            if await redis.ttl(key) <= 0:
                await redis.delete(key)
                cleaned += 1
        return cleaned
    except Exception as e:
        logger.error("cleanup_failed", pattern=pattern, error=str(e))
        return 0

# Initialize helpers
redis_helper = AsyncRedisHelper()
cache = AsyncCache(redis_helper)
rate_limiter = RateLimiter(redis_helper)

__all__ = [
    'redis_helper',
    'cache',
    'rate_limiter',
    'AsyncRedisLock',
    'cleanup_expired_keys'
]