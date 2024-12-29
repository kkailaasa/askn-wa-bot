# app/api/routes.py

from fastapi import APIRouter, Depends, Request, Form, HTTPException, Response
from fastapi.responses import RedirectResponse
import structlog
from datetime import datetime
from typing import Dict, Any, Optional
import phonenumbers
import json
from urllib.parse import urljoin

from app.core.config import settings
from app.db.database import get_db
from app.db.models import MessageLog, ErrorLog, RequestLog
from app.services.twilio import TwilioClient
from app.services.dify import DifyService
from app.services.load_balancer import LoadBalancer
from app.api.dependencies import rate_limit, verify_api_key
from app.utils.redis_helpers import cache
from app.worker.tasks import process_message

logger = structlog.get_logger()

router = APIRouter()
twilio_client = TwilioClient()
dify_service = DifyService()
load_balancer = LoadBalancer()

def validate_phone_number(phone_number: str) -> bool:
    """Validate phone number format"""
    try:
        number = phonenumbers.parse(phone_number, None)
        return phonenumbers.is_valid_number(number)
    except Exception:
        return False

def extract_cloudflare_data(request: Request) -> Dict[str, str]:
    """Extract CloudFlare headers from request"""
    return {
        "cf_ip": request.headers.get("CF-Connecting-IP"),
        "cf_country": request.headers.get("CF-IPCountry"),
        "cf_ray": request.headers.get("CF-RAY"),
        "cf_ssl": request.headers.get("CF-Visitor"),
        "user_agent": request.headers.get("User-Agent")
    }

@router.get("/message")
async def redirect_to_wa(
    request: Request,
    phone: Optional[str] = None,
    db = Depends(get_db),
    _=Depends(verify_api_key),
    __=Depends(rate_limit(100, 60))  # 100 requests per minute
):
    """Redirect to least loaded WhatsApp number"""
    start_time = datetime.utcnow()

    try:
        # Extract CloudFlare data
        cf_data = extract_cloudflare_data(request)

        # Validate phone number if provided
        if phone and not validate_phone_number(phone):
            raise HTTPException(status_code=400, detail="Invalid phone number")

        # Check cache for recent redirects
        cache_key = f"redirect:{cf_data['cf_ip']}"
        if await cache.get(cache_key):
            raise HTTPException(
                status_code=429,
                detail="Too many redirects. Please wait."
            )

        # Get least loaded number
        wa_number = await load_balancer.get_available_number()
        if not wa_number:
            raise HTTPException(
                status_code=503,
                detail="No available WhatsApp numbers"
            )

        # Format WhatsApp URL
        base_number = wa_number.replace('whatsapp:', '')
        wa_url = f"https://wa.me/{base_number}"
        if phone:
            wa_url += f"?phone={phone}"

        # Set redirect cache
        await cache.set(cache_key, True, expiry=30)  # 30 seconds cooldown

        # Log request
        request_log = RequestLog(
            twilio_number=wa_number,
            client_ip=cf_data["cf_ip"],
            cloudflare_data=cf_data,
            request_data={"redirect_url": wa_url, "phone": phone},
            response_status=302,
            processing_time=(datetime.utcnow() - start_time).total_seconds()
        )
        db.add(request_log)
        db.commit()

        return RedirectResponse(
            url=wa_url,
            status_code=302
        )

    except HTTPException:
        raise
    except Exception as e:
        # Log error
        error_log = ErrorLog(
            error_type=type(e).__name__,
            error_message=str(e),
            metadata={
                "from_number": From,
                "conversation_id": conversation_id if 'conversation_id' in locals() else None,
                "cloudflare_data": cf_data
            }
        )
        db.add(error_log)

        # Update request log with error info
        if 'request_log' in locals():
            request_log.response_status = 500
            request_log.processing_time = (datetime.utcnow() - start_time).total_seconds()

        db.commit()

        logger.error(
            "webhook_error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/health")
async def health_check(
    _=Depends(rate_limit(100, 60))  # 100 requests per minute
):
    """Health check endpoint with detailed service status"""
    try:
        # Get load balancer health
        lb_health = await load_balancer.health_check()

        # Check Dify service
        dify_health = await dify_service.health_check()

        # Check Twilio service
        twilio_health = await twilio_client.health_check()

        # Get Redis health
        redis_health = await cache.health_check()

        return {
            "status": "healthy" if all([
                lb_health["healthy"],
                dify_health,
                twilio_health,
                redis_health
            ]) else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "load_balancer": lb_health,
                "dify": "healthy" if dify_health else "unhealthy",
                "twilio": "healthy" if twilio_health else "unhealthy",
                "redis": "healthy" if redis_health else "unhealthy"
            },
            "version": settings.APP_VERSION
        }
    except Exception as e:
        logger.error("health_check_error", error=str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }

@router.get("/stats/load")
async def get_load_stats(
    request: Request,
    _=Depends(verify_api_key),
    __=Depends(rate_limit(settings.RATE_LIMIT_LOAD_STATS_LIMIT, settings.RATE_LIMIT_LOAD_STATS_PERIOD))
):
    """Get detailed load statistics for all WhatsApp numbers"""
    try:
        stats = await load_balancer.get_all_stats()

        # Calculate aggregate stats
        total_messages = sum(
            stat.get("message_count", 0)
            for stat in stats.values()
        )
        avg_load = sum(
            stat.get("current_load_percentage", 0)
            for stat in stats.values()
        ) / len(stats) if stats else 0

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "stats": stats,
            "aggregate": {
                "total_messages": total_messages,
                "average_load": avg_load,
                "active_numbers": len(stats)
            },
            "thresholds": {
                "high_load": settings.LOAD_BALANCER_HIGH_THRESHOLD * 100,
                "alert": settings.LOAD_BALANCER_ALERT_THRESHOLD * 100,
                "max_msgs_per_second": settings.MAX_MESSAGES_PER_SECOND
            },
            "window_size": settings.LOAD_BALANCER_STATS_WINDOW
        }
    except Exception as e:
        logger.error("load_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch load stats")

@router.get("/messages/{phone}")
async def get_message_history(
    phone: str,
    limit: int = 100,
    db = Depends(get_db),
    _=Depends(verify_api_key),
    __=Depends(rate_limit(50, 3600))  # 50 requests per hour
):
    """Get message history for a phone number with pagination"""
    try:
        # Validate phone number
        if not validate_phone_number(phone):
            raise HTTPException(status_code=400, detail="Invalid phone number")

        # Sanitize limit parameter
        limit = min(max(1, limit), 1000)  # Between 1 and 1000

        # Query messages with pagination
        messages = db.query(MessageLog).filter(
            MessageLog.from_number == phone
        ).order_by(
            MessageLog.timestamp.desc()
        ).limit(limit).all()

        return {
            "phone": phone,
            "total_messages": len(messages),
            "messages": [
                {
                    "timestamp": msg.timestamp.isoformat(),
                    "message": msg.message,
                    "response": msg.response,
                    "conversation_id": msg.conversation_id
                }
                for msg in messages
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "message_history_error",
            phone=phone,
            error=str(e)
        )
        # Create error log
        error_log = ErrorLog(
            error_type=type(e).__name__,
            error_message=str(e),
            error_metadata={  # Changed from metadata to error_metadata
                "cloudflare_data": cf_data if 'cf_data' in locals() else None,
                "phone": phone
            }
        )
        db.add(error_log)
        db.commit()

        raise HTTPException(
            status_code=500,
            detail="Failed to fetch message history"
        )

@router.post("/webhook")
async def handle_message(
    request: Request,
    Body: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    MessageSid: str = Form(...),
    NumMedia: Optional[int] = Form(0),
    MediaContentType0: Optional[str] = Form(None),
    MediaUrl0: Optional[str] = Form(None),
    db = Depends(get_db),
    __=Depends(rate_limit(100, 60))  # Keep only rate limiting
):
    """
    Handle incoming WhatsApp messages.
    Only performs immediate tasks:
    1. Validates request
    2. Checks for duplicates
    3. Logs incoming request
    4. Queues message for processing
    """
    start_time = datetime.utcnow()

    try:
        # Extract CloudFlare data
        cf_data = extract_cloudflare_data(request)

        # Check for duplicate message using MessageSid
        cache_key = f"message:sid:{MessageSid}"
        if await cache.get(cache_key):
            logger.info("duplicate_message_received", message_sid=MessageSid)
            return {"status": "success", "detail": "Duplicate message"}

        # Cache MessageSid to prevent duplicates
        await cache.set(cache_key, True, expiry=3600)  # 1 hour

        # Log incoming request immediately
        request_log = RequestLog(
            message_sid=MessageSid,
            twilio_number=To,
            client_ip=cf_data["cf_ip"],
            cloudflare_data=cf_data,
            request_data={
                "body": Body,
                "from": From,
                "to": To,
                "num_media": NumMedia,
                "media_type": MediaContentType0,
                "media_url": MediaUrl0
            }
        )
        db.add(request_log)

        # Prepare media data if present
        media_data = None
        if NumMedia and NumMedia > 0:
            media_data = {
                "type": MediaContentType0,
                "url": MediaUrl0
            }
            logger.info("media_received",
                       type=MediaContentType0,
                       url=MediaUrl0)

        # Queue the message processing task
        task = process_message.apply_async(
            kwargs={
                "message_sid": MessageSid,
                "from_number": From,
                "to_number": To,
                "body": Body,
                "media_data": media_data,
                "cloudflare_data": cf_data,
                "request_log_id": request_log.id
            },
            queue="high",
            priority=0
        )

        # Update request log
        request_log.task_id = task.id
        request_log.processing_time = (datetime.utcnow() - start_time).total_seconds()
        db.commit()

        return {
            "status": "accepted",
            "message": "Message queued for processing",
            "message_sid": MessageSid,
            "task_id": task.id
        }

    except Exception as e:
        # Error handling remains the same
        error_log = ErrorLog(
            error_type=type(e).__name__,
            error_message=str(e),
            metadata={
                "message_sid": MessageSid,
                "from_number": From,
                "cloudflare_data": cf_data if 'cf_data' in locals() else None
            }
        )
        db.add(error_log)

        if 'request_log' in locals():
            request_log.response_status = 500
            request_log.processing_time = (datetime.utcnow() - start_time).total_seconds()

        try:
            db.commit()
        except Exception as db_error:
            logger.error("db_commit_error", error=str(db_error))

        logger.error(
            "webhook_error",
            error=str(e),
            error_type=type(e).__name__,
            message_sid=MessageSid
        )

        return {
            "status": "error",
            "message": "Message received but queueing failed",
            "message_sid": MessageSid
        }