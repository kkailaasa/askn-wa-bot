from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger()

async def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler for uncaught exceptions"""
    logger.error(
        "uncaught_exception",
        exc_type=str(exc_type),
        exc_value=str(exc_value),
        exc_traceback=str(exc_traceback)
    )

async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=getattr(exc, 'status_code', 500),
        content={
            "detail": str(exc),
            "type": exc.__class__.__name__
        }
    )

def setup_exception_handlers(app: FastAPI):
    """Setup exception handlers for the FastAPI application"""
    app.add_exception_handler(Exception, http_exception_handler)
