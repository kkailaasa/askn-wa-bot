import urllib3
from typing import Dict
import logging
from urllib.parse import urlparse
import time

logger = logging.getLogger(__name__)

class HTTPClientPool:
    _instance = None
    _pools: Dict[str, urllib3.connectionpool.HTTPConnectionPool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(HTTPClientPool, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._pools = {}

    def get_pool(self, host: str, maxsize: int = 10, retries: int = 3, timeout: float = 10.0) -> urllib3.connectionpool.HTTPConnectionPool:
        try:
            if host not in self._pools:
                logger.debug(f"Creating new connection pool for {host}")

                # Parse the host to determine if it's HTTP or HTTPS
                parsed_url = urlparse(host if '://' in host else f'http://{host}')
                is_https = parsed_url.scheme == 'https'
                clean_host = parsed_url.netloc or parsed_url.path

                logger.debug(f"Creating {'HTTPS' if is_https else 'HTTP'} pool for {clean_host}")

                retry = urllib3.Retry(
                    total=retries,
                    backoff_factor=0.1,
                    status_forcelist=[500, 502, 503, 504],
                    allowed_methods=frozenset(['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'])
                )

                # Choose pool class based on protocol
                pool_class = urllib3.HTTPSConnectionPool if is_https else urllib3.HTTPConnectionPool

                pool = pool_class(
                    host=clean_host,
                    maxsize=maxsize,
                    retries=retry,
                    timeout=urllib3.Timeout(connect=timeout, read=timeout),
                    block=True
                )

                # For HTTPS, configure SSL context
                if is_https:
                    pool.conn_kw['ssl_context'] = urllib3.util.ssl_.create_urllib3_context(
                        cert_reqs=urllib3.util.ssl_.CERT_NONE  # For internal services, we can be lenient with SSL
                    )

                # Test connection before adding to pools
                try:
                    pool.urlopen('HEAD', '/', timeout=1.0)
                except Exception as e:
                    logger.warning(f"Initial connection test failed: {str(e)}")
                    # Continue anyway as the service might not support HEAD
                    pass

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
            # Retry the request once if it fails
            try:
                return pool.request(method, path, **kwargs)
            except Exception as e:
                logger.error(f"Retry request error for {host}: {str(e)}")
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
                'maxsize': pool.maxsize,
                'scheme': 'https' if isinstance(pool, urllib3.HTTPSConnectionPool) else 'http'
            }
        return {}

http_pool = HTTPClientPool()