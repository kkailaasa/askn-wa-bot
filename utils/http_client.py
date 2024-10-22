import urllib3
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class HTTPClientPool:
    _instance = None
    _pools: Dict[str, urllib3.HTTPSConnectionPool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(HTTPClientPool, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._pools = {}

    def get_pool(self, host: str, maxsize: int = 10, retries: int = 3) -> urllib3.HTTPSConnectionPool:
        try:
            if host not in self._pools:
                logger.debug(f"Creating new connection pool for {host}")
                retry = urllib3.Retry(
                    total=retries,
                    backoff_factor=0.1,
                    status_forcelist=[500, 502, 503, 504],
                    allowed_methods=frozenset(['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'])
                )

                pool = urllib3.HTTPSConnectionPool(
                    host=host,
                    maxsize=maxsize,
                    retries=retry,
                    timeout=urllib3.Timeout(connect=2.0, read=7.0),
                    block=True  # Block when pool is full
                )

                # Test connection before adding to pools
                pool.urlopen('HEAD', '/', timeout=1.0)
                self._pools[host] = pool

            return self._pools[host]

        except Exception as e:
            logger.error(f"Error creating pool for {host}: {str(e)}")
            # Cleanup failed pool
            if host in self._pools:
                self.close_pool(host)
            raise

    def request(self, host: str, method: str, path: str, **kwargs) -> urllib3.HTTPResponse:
        pool = self.get_pool(host)
        try:
            return pool.request(method, path, **kwargs)
        except Exception as e:
            logger.error(f"Request error for {host}: {str(e)}")
            raise

    def close_pool(self, host: str):
        if host in self._pools:
            logger.info(f"Closing pool for {host}")
            self._pools[host].close()
            del self._pools[host]

    def close_all(self):
        for host in list(self._pools.keys()):
            self.close_pool(host)

    def get_pool_stats(self, host: str) -> dict:
        if host in self._pools:
            pool = self._pools[host]
            return {
                'num_connections': len(pool.pool),
                'num_requests': pool.num_requests,
                'host': host,
                'maxsize': pool.maxsize
            }
        return {}

# redis_pool.py
import redis
from core.config import settings
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class RedisConnectionPool:
    _instance = None
    _pool: Optional[redis.ConnectionPool] = None

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
                health_check_interval=30,
                retry_on_timeout=True,
                retry_on_error=[redis.ConnectionError, redis.TimeoutError]
            )

    def get_client(self):
        try:
            client = redis.Redis(connection_pool=self._pool)
            # Test connection
            client.ping()
            return client

        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.error(f"Redis connection error: {str(e)}")
            self.close()  # Close pool on error
            raise
        except Exception as e:
            logger.error(f"Unexpected Redis error: {str(e)}")
            raise

    def close(self):
        if self._pool:
            logger.info("Closing Redis connection pool")
            self._pool.disconnect()
            self._pool = None

    def get_pool_stats(self) -> dict:
        if self._pool:
            return {
                'max_connections': self._pool.max_connections,
                'current_connections': len(self._pool._in_use_connections)
            }
        return {}

# In main.py, add a simple health check endpoint
@app.get("/health")
async def health_check():
    health_status = {
        "status": "healthy",
        "components": {
            "redis": check_redis_health(),
            "http_pools": check_http_pools_health()
        }
    }
    return health_status

def check_redis_health():
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

def check_http_pools_health():
    return {
        host: http_pool.get_pool_stats(host)
        for host in http_pool._pools.keys()
    }