import redis
from core.config import settings
import logging
import time
from typing import Optional
from redis.connection import ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError

logger = logging.getLogger(__name__)

class RedisConnectionPool:
    _instance = None
    _pool: Optional[ConnectionPool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisConnectionPool, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._pool is None:
            logger.info("Initializing Redis connection pool")
            try:
                self._pool = redis.ConnectionPool(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=0,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                    health_check_interval=30,
                    retry_on_timeout=True,
                    decode_responses=True  # Automatically decode responses to str
                )
            except Exception as e:
                logger.error(f"Failed to initialize Redis pool: {str(e)}")
                raise

    def get_client(self, max_retries: int = 3) -> redis.Redis:
        """Get Redis client with automatic retries"""
        if not self._pool:
            raise RuntimeError("Redis pool not initialized")

        backoff = 1
        last_error = None

        for attempt in range(max_retries):
            try:
                client = redis.Redis(connection_pool=self._pool)
                # Test connection
                client.ping()
                return client
            except (ConnectionError, TimeoutError) as e:
                last_error = e
                logger.warning(f"Redis connection attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= 2  # Exponential backoff
                    continue
                else:
                    logger.error("Max Redis connection retries reached")
                    raise

        raise last_error or RuntimeError("Failed to get Redis client")

    def _check_pool_health(self) -> bool:
        """Verify pool health and clean up dead connections"""
        try:
            with self._pool.get_connection('ping') as conn:
                conn.ping()
            return True
        except Exception as e:
            logger.error(f"Redis pool health check failed: {str(e)}")
            self._initialize_pool()  # Recreate pool on failure
            return False

    def _initialize_pool(self) -> None:
        """Initialize or reinitialize the connection pool"""
        try:
            self._pool = redis.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                health_check_interval=30,
                retry_on_timeout=True,
                decode_responses=True
            )
            logger.info("Redis pool reinitialized successfully")
        except Exception as e:
            logger.error(f"Failed to reinitialize Redis pool: {str(e)}")
            raise

    def close(self) -> None:
        """Close all connections in the pool"""
        if self._pool:
            logger.info("Closing Redis connection pool")
            self._pool.disconnect()
            self._pool = None

async def get_redis_with_retry(retries=3):
    """Get Redis connection with retries"""
    for attempt in range(retries):
        try:
            redis_client = get_redis_client()
            await redis_client.ping()
            return redis_client
        except Exception as e:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(1)

redis_pool = RedisConnectionPool()

def get_redis_client() -> redis.Redis:
    """Get a Redis client from the pool"""
    return redis_pool.get_client()

# Cleanup on module unload
import atexit
@atexit.register
def cleanup():
    if redis_pool:
        redis_pool.close()