import redis
from core.config import settings

# Create a connection pool
redis_pool = redis.ConnectionPool(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=0,
    max_connections=settings.REDIS_MAX_CONNECTIONS
)

def get_redis_client():
    return redis.Redis(connection_pool=redis_pool)