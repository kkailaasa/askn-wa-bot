# utils/operation_helpers.py

from typing import Optional, Dict, Any, Tuple, Callable, AsyncGenerator
import asyncio
import logging
import time
from datetime import datetime
from functools import wraps
from uuid import uuid4
from fastapi import Request
import structlog
from contextlib import asynccontextmanager

from core.sequence_errors import (
    SequenceException,
    SequenceErrorCode,
    SequenceResponse
)
from core.config import settings
from utils.logging_utils import log_error

logger = structlog.get_logger()

class RequestContext:
    """Request context holder"""
    _context = {}

    @classmethod
    def get_request_id(cls) -> Optional[str]:
        return cls._context.get("request_id")

    @classmethod
    def set_request_id(cls, request_id: str) -> None:
        cls._context["request_id"] = request_id

    @classmethod
    def clear(cls) -> None:
        cls._context.clear()

@asynccontextmanager
async def track_request(request: Request) -> AsyncGenerator[str, None]:
    """Context manager for request tracking"""
    request_id = str(uuid4())
    existing_request_id = request.headers.get("X-Request-ID")
    if existing_request_id:
        request_id = existing_request_id

    RequestContext.set_request_id(request_id)
    structured_logger = logger.bind(request_id=request_id)
    
    try:
        structured_logger.info(
            "request_started",
            path=request.url.path,
            method=request.method,
            client_ip=request.client.host
        )
        yield request_id
    finally:
        structured_logger.info("request_completed")
        RequestContext.clear()

def with_request_tracking(operation_name: str):
    """Decorator for request tracking and error handling"""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            async with track_request(request) as request_id:
                try:
                    background_tasks = kwargs.get('background_tasks')
                    result = await func(request, *args, **kwargs)
                    
                    if hasattr(result, 'headers'):
                        result.headers["X-Request-ID"] = request_id
                    
                    return result
                except Exception as e:
                    error = SequenceException(
                        error_code=(
                            e.error_code if isinstance(e, SequenceException)
                            else SequenceErrorCode.SYSTEM_ERROR
                        ),
                        message=str(e),
                        status_code=getattr(e, 'status_code', 500)
                    )
                    
                    if background_tasks:
                        background_tasks.add_task(
                            log_error,
                            error_type=type(error).__name__,
                            error_message=str(error),
                            metadata={
                                "request_id": request_id,
                                "operation": operation_name
                            }
                        )
                    raise error
        return wrapper
    return decorator

async def safe_operation_execution(
    operation: str,
    func: Callable,
    timeout: int,
    **kwargs
) -> Any:
    """Execute any operation safely with timeout"""
    try:
        async with asyncio.timeout(timeout):
            if asyncio.iscoroutinefunction(func):
                return await func(**kwargs)
            if hasattr(func, 'delay'):  # Celery task
                task = func.delay(**kwargs)
                return await asyncio.wait_for(task.get(), timeout=timeout-2)
            return func(**kwargs)
            
    except asyncio.TimeoutError:
        logger.error(f"Operation {operation} timed out")
        raise SequenceException(
            error_code=SequenceErrorCode.TIMEOUT,
            message=f"Operation {operation} timed out",
            status_code=503,
            retry_after=30
        )
    except Exception as e:
        logger.error(f"Operation {operation} failed: {str(e)}")
        raise SequenceException(
            error_code=SequenceErrorCode.SYSTEM_ERROR,
            message=f"Operation {operation} failed",
            status_code=500,
            details={"error": str(e)}
        )

async def check_system_health() -> Dict[str, Any]:
    """Check system components health"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION,
        "components": {}
    }

    # Check Redis
    try:
        async with asyncio.timeout(2):
            redis_start = time.time()
            await safe_operation_execution(
                "redis_health_check",
                redis_client.ping,
                2
            )
            redis_latency = time.time() - redis_start
            health_status["components"]["redis"] = {
                "status": "healthy",
                "latency_ms": round(redis_latency * 1000, 2)
            }
    except Exception as e:
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"

    # Check Keycloak
    try:
        async with asyncio.timeout(2):
            auth_start = time.time()
            await safe_operation_execution(
                "keycloak_health_check",
                auth_service.health_check,
                2
            )
            auth_latency = time.time() - auth_start
            health_status["components"]["keycloak"] = {
                "status": "healthy",
                "latency_ms": round(auth_latency * 1000, 2)
            }
    except Exception as e:
        health_status["components"]["keycloak"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"

    return health_status