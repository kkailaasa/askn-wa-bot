from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import structlog

logger = structlog.get_logger()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        logger.info(
            "request_processed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=f"{process_time:.3f}s"
        )
        
        response.headers["X-Process-Time"] = str(process_time)
        return response

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Add basic metrics headers
        response.headers["X-Response-Time"] = str(process_time)
        return response

class ClientIPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if "X-Forwarded-For" in request.headers:
            request.state.client_ip = request.headers["X-Forwarded-For"].split(",")[0]
        else:
            request.state.client_ip = request.client.host
        
        response = await call_next(request)
        return response
