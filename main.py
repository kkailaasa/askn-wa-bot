# main.py

import structlog
import uvicorn
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time

# Local imports
from app.api.routes import router as api_router
from app.core.config import settings
from app.db.database import Base, engine
from app.services.load_balancer import LoadBalancer
from app.services.dify import DifyService
from app.services.twilio import TwilioClient
from app.utils.redis_helpers import cache

# Configure logging
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager for the FastAPI application
    Handles startup and shutdown events
    """
    # Startup
    try:
        # Create database tables
        Base.metadata.create_all(bind=engine)

        # Initialize services
        lb = LoadBalancer()
        dify = DifyService()
        twilio = TwilioClient()

        # Check Redis connection
        if not await cache.ping():
            logger.error("redis_connection_failed")
            
        logger.info(
            "application_startup",
            app_name=settings.APP_NAME,
            version=settings.APP_VERSION,
            environment=settings.ENVIRONMENT
        )

    except Exception as e:
        logger.error("startup_error", error=str(e))
        raise

    yield

    # Shutdown
    try:
        # Close any connections
        await cache.close()
        logger.info("application_shutdown")
    except Exception as e:
        logger.error("shutdown_error", error=str(e))

# Initialize FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="WhatsApp Bot API",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        logger.info(
            "request_processed",
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration=time.time() - start_time,
            client_ip=request.headers.get("CF-Connecting-IP", request.client.host)
        )
        return response
    except Exception as e:
        logger.error(
            "request_failed",
            path=request.url.path,
            method=request.method,
            error=str(e),
            duration=time.time() - start_time
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Include routers
app.include_router(api_router, prefix="/api")

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint returning basic application info"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }

# Health check endpoint
@app.get("/health")
async def health():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": settings.APP_VERSION
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG
    )