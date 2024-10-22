# utils/http_client.py
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

http_pool = HTTPClientPool()