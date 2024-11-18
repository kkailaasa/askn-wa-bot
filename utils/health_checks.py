import redis.asyncio as redis_async
from typing import Dict, Any
import psutil
import structlog

logger = structlog.get_logger()

async def check_redis_health(redis_client: redis_async.Redis) -> Dict[str, Any]:
    """Check Redis connection health"""
    try:
        await redis_client.ping()
        return {
            "status": "healthy",
            "details": "Redis connection is working"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

async def check_db_health() -> Dict[str, Any]:
    """Check database health"""
    # Implement your database health check here
    # This is a placeholder implementation
    return {
        "status": "healthy",
        "details": "Database connection is working"
    }

async def check_dependencies_health() -> Dict[str, Any]:
    """Check all dependencies health"""
    return {
        "redis": await check_redis_health(),
        "database": await check_db_health(),
        "system": {
            "memory_usage": psutil.Process().memory_info().rss,
            "cpu_percent": psutil.Process().cpu_percent(),
            "thread_count": psutil.Process().num_threads()
        }
    }
