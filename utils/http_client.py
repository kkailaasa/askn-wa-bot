import urllib3
from typing import Dict, Optional, Union, Any
import structlog
from urllib.parse import urlparse
import time
import json
import ssl
from core.config import settings
from core.sequence_errors import SequenceException, SequenceErrorCode
import asyncio
from datetime import datetime, timedelta
from utils.redis_helpers import cache

logger = structlog.get_logger(__name__)

class HTTPResponse:
    """Wrapper for urllib3 response with additional functionality"""
    def __init__(self, response: urllib3.HTTPResponse):
        self.raw_response = response
        self.status = response.status
        self.data = response.data
        self.headers = response.headers
        self._cached_json = None

    @property
    def content(self) -> bytes:
        return self.data

    def json(self) -> Dict[str, Any]:
        """Parse JSON response with caching"""
        if self._cached_json is None:
            try:
                self._cached_json = json.loads(self.data.decode('utf-8'))
            except json.JSONDecodeError as e:
                raise SequenceException(
                    error_code=SequenceErrorCode.INVALID_DATA,
                    message=f"Invalid JSON response: {str(e)}"
                )
        return self._cached_json

class PoolStats:
    """Track pool statistics"""
    def __init__(self):
        self.requests_made = 0
        self.errors = 0
        self.last_error_time = None
        self.avg_response_time = 0
        self.total_response_time = 0

    def record_request(self, response_time: float):
        """Record request statistics"""
        self.requests_made += 1
        self.total_response_time += response_time
        self.avg_response_time = self.total_response_time / self.requests_made

    def record_error(self):
        """Record error statistics"""
        self.errors += 1
        self.last_error_time = datetime.utcnow()

class HTTPClientPool:
    """Enhanced HTTP client pool with monitoring and safety features"""
    _instance = None
    _pools: Dict[str, urllib3.connectionpool.HTTPConnectionPool] = {}
    _stats: Dict[str, PoolStats] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(HTTPClientPool, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self._pools = {}
            self._stats = {}
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            logger.info("http_client_pool_initialized")

    def _get_ssl_context(self):
        """Get appropriate SSL context"""
        if settings.ENVIRONMENT == "development":
            return ssl.create_default_context()
        context = ssl.create_default_context()
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        return context

    def get_pool(
        self,
        host: str,
        maxsize: Optional[int] = None,
        retries: int = 3,
        timeout: float = 10.0,
        ssl_context: Optional[ssl.SSLContext] = None
    ) -> urllib3.connectionpool.HTTPConnectionPool:
        """Get or create connection pool with enhanced error handling"""
        try:
            if host not in self._pools:
                logger.debug("creating_connection_pool", host=host)

                # Parse URL properly
                parsed_url = urlparse(host if '://' in host else f'http://{host}')
                is_https = parsed_url.scheme == 'https'
                clean_host = parsed_url.netloc or parsed_url.path

                # Set maxsize from settings if not provided
                if maxsize is None:
                    maxsize = settings.HTTP_POOL_MAX_SIZE

                # Configure retries
                retry = urllib3.Retry(
                    total=retries,
                    backoff_factor=0.1,
                    status_forcelist=[500, 502, 503, 504],
                    allowed_methods=frozenset(['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS']),
                    raise_on_status=False
                )

                # Pool configuration
                pool_kwargs = {
                    'host': clean_host,
                    'maxsize': maxsize,
                    'retries': retry,
                    'timeout': urllib3.Timeout(connect=timeout, read=timeout),
                    'block': True
                }

                # Choose pool class based on protocol
                pool_class = urllib3.HTTPSConnectionPool if is_https else urllib3.HTTPConnectionPool

                # Configure SSL for HTTPS
                if is_https:
                    if ssl_context:
                        pool_kwargs['ssl_context'] = ssl_context
                    else:
                        pool_kwargs['ssl_context'] = urllib3.util.ssl_.create_urllib3_context(
                            cert_reqs=ssl.CERT_NONE if settings.ENVIRONMENT == "development" else ssl.CERT_REQUIRED
                        )

                # Create and store pool
                self._pools[host] = pool_class(**pool_kwargs)
                self._stats[host] = PoolStats()

                logger.info(
                    "connection_pool_created",
                    host=clean_host,
                    is_https=is_https,
                    max_size=maxsize
                )

            return self._pools[host]

        except Exception as e:
            logger.error(
                "pool_creation_failed",
                host=host,
                error=str(e),
                error_type=type(e).__name__
            )
            if host in self._pools:
                self.close_pool(host)
            raise SequenceException(
                error_code=SequenceErrorCode.NETWORK_ERROR,
                message=f"Failed to create connection pool for {host}"
            )

    async def request(
        self,
        host: str,
        method: str,
        path: str,
        retries: int = 3,
        timeout: Optional[float] = None,
        **kwargs
    ) -> HTTPResponse:
        """Make HTTP request with enhanced error handling and monitoring"""
        start_time = time.time()
        last_error = None
        pool = self.get_pool(host)

        for attempt in range(retries):
            try:
                # Add request tracking headers
                headers = kwargs.get('headers', {})
                headers.update({
                    'X-Request-ID': str(time.time()),
                    'X-Attempt': str(attempt + 1)
                })
                kwargs['headers'] = headers

                # Make request with timeout
                async with asyncio.timeout(timeout or settings.HTTP_POOL_TIMEOUT):
                    response = pool.request(method, path, **kwargs)

                    # Record statistics
                    response_time = time.time() - start_time
                    self._stats[host].record_request(response_time)

                    return HTTPResponse(response)

            except (urllib3.exceptions.TimeoutError, asyncio.TimeoutError) as e:
                last_error = SequenceException(
                    error_code=SequenceErrorCode.TIMEOUT,
                    message=f"Request to {host} timed out",
                    status_code=504
                )
            except Exception as e:
                last_error = e
                self._stats[host].record_error()

            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            break

        logger.error(
            "request_failed",
            host=host,
            method=method,
            path=path,
            attempts=attempt + 1,
            error=str(last_error)
        )

        raise last_error or SequenceException(
            error_code=SequenceErrorCode.NETWORK_ERROR,
            message=f"Request to {host} failed after {retries} attempts"
        )

    def close_pool(self, host: str) -> None:
        """Close and cleanup specific pool"""
        if host in self._pools:
            logger.info("closing_connection_pool", host=host)
            try:
                self._pools[host].close()
                del self._pools[host]
                del self._stats[host]
            except Exception as e:
                logger.error(
                    "pool_closure_failed",
                    host=host,
                    error=str(e)
                )

    def close_all(self) -> None:
        """Close all connection pools"""
        for host in list(self._pools.keys()):
            self.close_pool(host)

    def get_pool_stats(self, host: str) -> Dict[str, Any]:
        """Get detailed pool statistics"""
        if host in self._pools:
            pool = self._pools[host]
            stats = self._stats[host]

            return {
                'host': host,
                'scheme': 'https' if isinstance(pool, urllib3.HTTPSConnectionPool) else 'http',
                'maxsize': pool.maxsize,
                'num_connections': len(pool.pool),
                'requests_made': stats.requests_made,
                'errors': stats.errors,
                'last_error_time': stats.last_error_time.isoformat() if stats.last_error_time else None,
                'avg_response_time': stats.avg_response_time
            }
        return {}

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all pools"""
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'pools': {}
        }

        for host in self._pools:
            pool_stats = self.get_pool_stats(host)
            recent_errors = pool_stats.get('errors', 0) > 0 and \
                          pool_stats.get('last_error_time') and \
                          datetime.fromisoformat(pool_stats['last_error_time']) > \
                          datetime.utcnow() - timedelta(minutes=5)

            health_status['pools'][host] = {
                'status': 'degraded' if recent_errors else 'healthy',
                'stats': pool_stats
            }

            if recent_errors:
                health_status['status'] = 'degraded'

        return health_status

# Initialize singleton instance
http_pool = HTTPClientPool()

# Cleanup on module unload
import atexit
@atexit.register
def cleanup():
    if http_pool:
        http_pool.close_all()