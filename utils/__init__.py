# utils/__init__.py

from utils.redis_pool import get_redis_client
redis_sync_client = get_redis_client()  # For any code that still needs sync client

from .redis_helpers import (
    redis_helper,  # Instead of redis_client
    rate_limiter,
    AsyncRedisLock,
    cleanup_expired_keys,
    cache
)

from .operation_helpers import (
    safe_operation_execution,
    check_system_health,
    with_request_tracking,
    RequestContext,
    track_request
)

from .logging_utils import (
    log_error,
    log_conversation
)

from .validators import (
    validate_phone_format,
    validate_email_format,
    validate_name_format,
    validate_gender,
    validate_country
)

__all__ = [
    # Redis Helpers
    'redis_helper',
    'redis_sync_client',
    'rate_limiter',
    'AsyncRedisLock',
    'cleanup_expired_keys',
    'cache',

    # Operation Helpers
    'safe_operation_execution',
    'check_system_health',
    'with_request_tracking',
    'RequestContext',
    'track_request',

    # Logging Utils
    'log_error',
    'log_conversation',

    # Validators
    'validate_phone_format',
    'validate_email_format',
    'validate_name_format',
    'validate_gender',
    'validate_country'
]