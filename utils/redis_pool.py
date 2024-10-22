import redis
from core.config import settings
import logging

logger = logging.getLogger(__name__)

class RedisConnectionPool:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisConnectionPool, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._pool is None:
            logger.info("Initializing Redis connection pool")
            self._pool = redis.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                health_check_interval=30
            )

    @property
    def pool(self):
        return self._pool

    def close(self):
        if self._pool:
            logger.info("Closing Redis connection pool")
            self._pool.disconnect()
            self._pool = None

redis_pool = RedisConnectionPool()

def get_client(self):
        try:
            client = redis.Redis(connection_pool=self._pool)
            client.ping()  # Test connection
            return client
        except redis.ConnectionError as e:
            logger.error(f"Failed to get Redis client: {str(e)}")
            self.close()  # Close pool on error
            raise

def get_redis_client():
    try:
        return redis_pool.get_client()
    except Exception as e:
        logger.error(f"Error getting Redis client: {str(e)}")
        raise