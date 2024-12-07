# app/api/dependencies.py

from fastapi import HTTPException, Request, Depends
from twilio.request_validator import RequestValidator
from typing import Callable
import time
from app.core.config import settings
import structlog
from collections import defaultdict

logger = structlog.get_logger()

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def is_rate_limited(self, key: str, limit: int, period: int) -> bool:
        now = time.time()

        # Remove old requests
        self.requests[key] = [req_time for req_time in self.requests[key]
                            if now - req_time < period]

        # Check if limit is exceeded
        if len(self.requests[key]) >= limit:
            return True

        # Add new request
        self.requests[key].append(now)
        return False

rate_limiter = RateLimiter()

def rate_limit(limit: int, period: int) -> Callable:
    async def rate_limit_dependency(request: Request):
        client_ip = request.headers.get("CF-Connecting-IP", request.client.host)

        if rate_limiter.is_rate_limited(client_ip, limit, period):
            logger.warning(
                "rate_limit_exceeded",
                ip=client_ip,
                endpoint=request.url.path
            )
            raise HTTPException(
                status_code=429,
                detail="Too many requests"
            )

        return True
    return rate_limit_dependency

async def verify_api_key(request: Request) -> bool:
    """Verify API key from headers"""
    api_key = request.headers.get('X-API-Key')

    if not api_key or api_key != settings.API_KEY:
        logger.warning(
            "invalid_api_key",
            ip=request.headers.get("CF-Connecting-IP", request.client.host)
        )
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )

    return True

async def validate_twilio_signature(request: Request):
    """
    Validates that the request is coming from Twilio

    Twilio sends these headers:
    - X-Twilio-Signature: Used to validate request
    - X-Twilio-IdempotencyToken: Unique token for the request (optional)
    """

    # Get Twilio signature from header
    twilio_signature = request.headers.get("X-Twilio-Signature")
    if not twilio_signature:
        logger.warning("missing_twilio_signature",
                      ip=request.client.host)
        raise HTTPException(status_code=403, detail="Missing Twilio signature")

    # Get full URL for validation
    # Twilio uses the full URL including scheme, host, path and query string
    url = str(request.base_url)[:-1] + request.url.path

    try:
        # Get request body as form data
        # Important: We need to await the form() here to get the data
        form_data = await request.form()

        # Convert form data to dict for validation
        post_vars = dict(form_data)

        # Create validator with our auth token
        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)

        # Validate request
        is_valid = validator.validate(
            url,
            post_vars,
            twilio_signature
        )

        if not is_valid:
            logger.warning("invalid_twilio_signature",
                         ip=request.client.host,
                         url=url)
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

        return True

    except Exception as e:
        logger.error("twilio_validation_error",
                    error=str(e),
                    error_type=type(e).__name__)
        raise HTTPException(status_code=403, detail="Signature validation failed")