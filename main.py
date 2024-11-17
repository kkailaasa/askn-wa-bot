from fastapi import FastAPI, Request, Response, BackgroundTasks
from pydantic import ValidationError
from db_scripts.base import get_db, get_db_dependency, AsyncSessionLocal
from fastapi.middleware.cors import CORSMiddleware
from api.load_balancer import router as load_balancer_router, signup_endpoint
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi import Security, HTTPException, status
from contextlib import asynccontextmanager
import uvicorn
import redis.asyncio as redis_async
from api.routes import router
from core.config import Settings
from core.sequence_errors import (
    SequenceException,
    SequenceErrorCode,
    handle_sequence_error,
    ErrorContext
)
from utils.http_client import http_pool
from utils.redis_pool import redis_pool, get_redis_client
from utils.redis_helpers import AsyncRedisLock, cleanup_expired_keys
from utils.logging_utils import log_error
from services import auth_service, email_service, ChatService
from services.email_service import EmailService
import sys
import atexit
import time
from datetime import datetime
import json
from typing import Dict, Any, Optional, Union
import structlog
import logging.config
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import socket
import platform
import psutil
import ipaddress
from pathlib import Path

# Initialize logging
logger = structlog.get_logger(__name__)

# Configure logging level based on environment
logging_level = logging.DEBUG if Settings().DEBUG else logging.INFO

# Configure custom JSON processor for structlog
def custom_json_processor(_, __, event_dict):
    """Custom JSON processor to handle non-serializable types"""
    def serializer(obj):
        if isinstance(obj, (datetime, time.struct_time)):
            return obj.isoformat()
        return str(obj)

    return json.loads(json.dumps(event_dict, default=serializer))

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True
)

# Initialize logger
logger = structlog.get_logger()

# Initialize settings
try:
    settings = Settings()
except ValidationError as e:
    logger.error(f"Configuration error: {e}")
    sys.exit(1)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Enhanced request/response logging middleware"""
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        request_id = request.headers.get("X-Request-ID", str(time.time()))
        cf_ray = request.headers.get("cf-ray", "")

        # Get all relevant client info
        client_info = {
            "ip": request.client.host,
            "cf_ip": request.headers.get("cf-connecting-ip"),
            "cf_country": request.headers.get("cf-ipcountry"),
            "cf_ray": cf_ray,
            "forwarded_for": request.headers.get("x-forwarded-for"),
            "user_agent": request.headers.get("user-agent"),
            "real_scheme": request.headers.get("x-forwarded-proto", request.url.scheme)
        }

        # Enhanced request logging
        logger.info(
            "request_started",
            request_id=request_id,
            method=request.method,
            url=str(request.url),
            client=client_info,
            path_params=dict(request.path_params),
            query_params=dict(request.query_params)
        )

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Enhanced response logging
            logger.info(
                "request_completed",
                request_id=request_id,
                status_code=response.status_code,
                process_time=process_time,
                content_type=response.headers.get("content-type"),
                content_length=response.headers.get("content-length"),
                cf_ray=cf_ray
            )

            # Add response headers
            response.headers["X-Process-Time"] = f"{process_time:.4f}"
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            logger.error(
                "request_failed",
                request_id=request_id,
                error=str(e),
                error_type=type(e).__name__,
                client=client_info,
                cf_ray=cf_ray,
                traceback=True
            )
            raise

class MetricsMiddleware(BaseHTTPMiddleware):
    """Collect and track application metrics"""
    def __init__(self, app):
        super().__init__(app)
        self.process = psutil.Process()

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        try:
            response = await call_next(request)

            # Collect metrics
            metrics = {
                'response_time': time.time() - start_time,
                'memory_usage': self.process.memory_info().rss,
                'cpu_percent': self.process.cpu_percent(),
                'thread_count': self.process.num_threads(),
                'open_files': len(self.process.open_files()),
                'connections': len(self.process.connections())
            }

            logger.debug("request_metrics", **metrics)
            return response

        except Exception:
            raise

# Create async Redis client
async def init_redis() -> redis_async.Redis:
    for retry in range(3):  # Add retries
        try:
            redis = redis_async.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                retry_on_timeout=True
            )
            await redis.ping()  # Test connection
            return redis
        except Exception as e:
            if retry == 2:  # Last retry
                logger.error("Redis initialization failed", error=str(e))
                raise
            await asyncio.sleep(1)  # Wait before retry

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(
        "application_startup",
        environment=settings.ENVIRONMENT,
        python_version=platform.python_version(),
        system=platform.system()
    )

    try:
        # Initialize Redis async client
        app.state.redis = await init_redis()

        # Test Redis connection
        await app.state.redis.ping()
        logger.info("redis_connection_established")

        # Clean stale data
        async for key in app.state.redis.scan_iter("sequence:*"):
            await app.state.redis.delete(key)
        async for key in app.state.redis.scan_iter("lock:*"):
            await app.state.redis.delete(key)

        # Initialize health check cache
        health_status = {
            'status': 'starting',
            'startup_time': datetime.utcnow().isoformat(),
            'version': settings.APP_VERSION
        }
        await app.state.redis.setex(
            'health:status',
            3600,
            json.dumps(health_status)
        )

        # Create required directories
        Path("logs").mkdir(exist_ok=True)
        Path("temp").mkdir(exist_ok=True)
        Path("templates").mkdir(exist_ok=True)

        # Initialize email templates
        await email_service.initialize_templates()

        logger.info("application_startup_completed")

    except Exception as e:
        logger.error("startup_failed", error=str(e))
        raise

    try:
        yield
    finally:
        # Shutdown
        logger.info("application_shutdown_started")
        try:
            # Close Redis connection
            await app.state.redis.close()
            logger.info("redis_connection_closed")

            # Clean temporary files
            for temp_file in Path("temp").glob("*"):
                temp_file.unlink()

            logger.info("application_shutdown_completed")
        except Exception as e:
            logger.error("shutdown_error", error=str(e))


class ClientIPMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope["headers"])

            # Try to get real IP in order of preference
            real_ip = None

            # First check Cloudflare headers
            cf_connecting_ip = headers.get(b"cf-connecting-ip", b"").decode()
            if cf_connecting_ip:
                real_ip = cf_connecting_ip

            # Then check X-Forwarded-For
            elif b"x-forwarded-for" in headers:
                # Get the first IP in X-Forwarded-For chain
                forwarded_for = headers[b"x-forwarded-for"].decode().split(",")[0].strip()
                try:
                    # Validate IP address
                    ipaddress.ip_address(forwarded_for)
                    real_ip = forwarded_for
                except ValueError:
                    pass

            # Finally check X-Real-IP
            elif b"x-real-ip" in headers:
                real_ip = headers[b"x-real-ip"].decode()

            if real_ip:
                # Update client host and port in scope
                scope["client"] = (real_ip, scope["client"][1])

        return await self.app(scope, receive, send)


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
)

# Middleware configuration
app.add_middleware(ClientIPMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.DEBUG else settings.CORS_ALLOWED_ORIGINS
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"]
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(MetricsMiddleware)


@app.get("/signup")
async def signup_route(request: Request, background_tasks: BackgroundTasks):
    return await signup_endpoint(request, background_tasks)

# Mount other routers
app.include_router(router, prefix="/api")
app.include_router(load_balancer_router, prefix="/api/lb")

@app.exception_handler(SequenceException)
async def sequence_exception_handler(request: Request, exc: SequenceException):
    """Enhanced sequence exception handler"""
    error_context = ErrorContext(
        timestamp=datetime.utcnow().isoformat(),
        error_code=exc.error_code,
        message=str(exc),
        details={
            'path': str(request.url),
            'method': request.method,
            'client_ip': request.client.host,
            'request_id': request.headers.get("X-Request-ID")
        }
    )

    logger.error(
        "sequence_error",
        error_code=exc.error_code,
        error_message=str(exc),
        request_id=request.headers.get("X-Request-ID"),
        client_ip=request.client.host,
        error_context=error_context.dict()
    )

    try:
        await log_error(
            error_type="SequenceException",
            error_message=str(exc),
            metadata=error_context.dict()
        )
    except Exception as log_err:
        logger.error(f"Failed to log error: {str(log_err)}")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": str(exc),
            "request_id": request.headers.get("X-Request-ID")
        },
        headers=getattr(exc, 'headers', None)
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Enhanced global exception handler"""
    error_details = {
        'path': str(request.url),
        'method': request.method,
        'client_ip': request.client.host,
        'headers': {
            k: v for k, v in request.headers.items()
            if k.lower() not in ['authorization', 'cookie', 'x-api-key']
        }
    }

    # Get request body for non-sensitive endpoints
    if request.method in ['POST', 'PUT'] and request.url.path not in ['/api/message']:
        try:
            body = await request.body()
            if body:
                error_details["body"] = json.loads(body.decode())
        except Exception:
            pass

    logger.error(
        "unhandled_error",
        error_type=type(exc).__name__,
        error_message=str(exc),
        request_id=request.headers.get("X-Request-ID"),
        client_ip=request.client.host,
        details=error_details,
        traceback=True
    )

    # Use async version of log_error
    try:
        await log_error(
            error_type=type(exc).__name__,
            error_message=str(exc),
            metadata=error_details
        )
    except Exception as log_error:
        logger.error(f"Failed to log error: {str(log_error)}")

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": request.headers.get("X-Request-ID")
        }
    )

# Custom logging handler for uncaught exceptions
def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception hook for uncaught exceptions"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error(
        "uncaught_exception",
        error_type=exc_type.__name__,
        error_message=str(exc_value),
        traceback=True
    )

sys.excepthook = handle_exception

async def check_dependencies_health():
    """Check all dependencies"""
    return {
        "redis": await check_redis_health(),
        "database": await check_db_health(),
        "keycloak": await auth_service.health_check(),
        "email": await email_service.health_check(),
        "dify": await ChatService.health_check()
    }

@app.get("/api/health")
async def health_check():
    """Enhanced health check endpoint"""
    try:
        redis_client = get_redis_client()
        cached_status = await redis_client.get('health:status')
        base_status = json.loads(cached_status) if cached_status else {}

        current_status = {
            **base_status,
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "components": await check_dependencies_health(),
            "system": {
                "memory_usage": psutil.Process().memory_info().rss,
                "cpu_percent": psutil.Process().cpu_percent(),
                "thread_count": psutil.Process().num_threads(),
                "open_files": len(psutil.Process().open_files()),
                "connections": len(psutil.Process().connections())
            }
        }

        # Update status in cache
        await redis_client.setex(
            'health:status',
            3600,
            json.dumps(current_status)
        )

        return current_status

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }

async def load_balancer_health():
    try:
        if not settings.TWILIO_NUMBERS:
            return {
                "status": "unhealthy",
                "error": "No Twilio numbers configured"
            }

        numbers = [num.strip() for num in settings.TWILIO_NUMBERS.split(',') if num.strip()]
        loads = {}
        for num in numbers:
            try:
                loads[num] = await load_balancer.get_number_load(num)
            except Exception as e:
                logger.error(f"Failed to get load for number {num}: {e}")
                loads[num] = None

        return {
            "status": "healthy" if all(load is not None for load in loads.values()) else "degraded",
            "current_loads": loads,
            "max_messages": settings.MAX_MESSAGES_PER_SECOND,
            "high_threshold": load_balancer.high_threshold
        }
    except Exception as e:
        logger.error("Load balancer health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e)
        }


async def check_redis_health() -> Dict[str, Any]:
    """Check Redis connection health"""
    try:
        redis_client = get_redis_client()
        start_time = time.time()
        await redis_client.ping()
        latency = time.time() - start_time

        info = await redis_client.info()
        return {
            "status": "healthy",
            "latency": latency,
            "connected_clients": info.get("connected_clients"),
            "used_memory": info.get("used_memory_human"),
            "version": info.get("redis_version")
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

async def check_db_health() -> Dict[str, Any]:
    """Check database health"""
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        log_level="info",
        reload=settings.DEBUG,
        workers=4,
        forwarded_allow_ips="*"
    )