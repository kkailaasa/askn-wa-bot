import asyncio
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import redis.asyncio as redis_async
import uvicorn
import structlog
import logging
import sys
import json
import time
from datetime import datetime
from pathlib import Path
import platform
import psutil
import ipaddress

from core.config import Settings
from core.logging_config import configure_logging
from core.middleware import (
    RequestLoggingMiddleware,
    MetricsMiddleware,
    ClientIPMiddleware
)
from core.exception_handlers import (
    setup_exception_handlers,
    handle_uncaught_exception
)
from api.routes import router
from api.load_balancer import router as load_balancer_router, signup_endpoint
from services import auth_service, email_service, ChatService
from utils.health_checks import (
    check_dependencies_health,
    check_redis_health,
    check_db_health
)

# Initialize settings and logging
settings = Settings()
logger = configure_logging(settings.DEBUG)
async def init_redis() -> redis_async.Redis:
    """Initialize Redis connection with retries"""
    for retry in range(3):
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
            await redis.ping()
            return redis
        except Exception as e:
            if retry == 2:
                logger.error("Redis initialization failed", error=str(e))
                raise
            await asyncio.sleep(1)

async def initialize_application():
    """Initialize application dependencies"""
        # Create required directories
    for directory in ["logs", "temp", "templates"]:
        Path(directory).mkdir(exist_ok=True)
        # Initialize email templates
        await email_service.initialize_templates()

async def cleanup_redis(redis_client):
    """Clean up Redis data"""
    patterns = ["sequence:*", "lock:*"]
    for pattern in patterns:
        async for key in redis_client.scan_iter(pattern):
            await redis_client.delete(key)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info(
        "application_startup",
        environment=settings.ENVIRONMENT,
        python_version=platform.python_version(),
        system=platform.system()
)

    try:
        # Initialize Redis
        app.state.redis = await init_redis()
        logger.info("redis_connection_established")

        # Clean up Redis and initialize application
        await cleanup_redis(app.state.redis)
        await initialize_application()

        # Set initial health status
        health_status = {
            'status': 'healthy',
            'startup_time': datetime.utcnow().isoformat(),
            'version': settings.APP_VERSION
        }
        await app.state.redis.setex(
            'health:status',
            3600,
            json.dumps(health_status)
        )

        logger.info("application_startup_completed")
        yield
    except Exception as e:
        logger.error("startup_failed", error=str(e))
        raise
    finally:
        # Shutdown cleanup
        logger.info("application_shutdown_started")
        try:
            if hasattr(app.state, 'redis'):
                await app.state.redis.close()
            
            # Clean temporary files
            for temp_file in Path("temp").glob("*"):
                temp_file.unlink()
                
            logger.info("application_shutdown_completed")
        except Exception as e:
            logger.error("shutdown_error", error=str(e))

def create_application() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
    )

    # Add middleware
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

    # Set up routes
    app.include_router(router, prefix="/api")
    app.include_router(load_balancer_router, prefix="/api/lb")
    app.get("/signup")(signup_endpoint)
    app.get("/api/health")(health_check)

    # Set up exception handlers
    setup_exception_handlers(app)
    sys.excepthook = handle_uncaught_exception

    return app

async def health_check():
    """Health check endpoint"""
    try:
        current_status = {
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

        await app.state.redis.setex(
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

# Create application instance
app = create_application()

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