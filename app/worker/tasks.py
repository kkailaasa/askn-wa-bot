# app/worker/tasks.py

from celery import shared_task
from app.worker.celery_app import celery_app
from app.services.dify import DifyService
from app.services.twilio import TwilioClient
from app.services.load_balancer import LoadBalancer
from app.db.database import SessionLocal
from app.db.models import MessageLog, ErrorLog
import structlog
from datetime import datetime
from typing import Optional, Dict, Any

logger = structlog.get_logger()

# Initialize services
dify_service = DifyService()
twilio_client = TwilioClient()
load_balancer = LoadBalancer()

@shared_task(
    name="process_message",
    queue="high",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True
)
def process_message(
    message_sid: str,
    from_number: str,
    to_number: str,
    body: str,
    media_data: Optional[Dict[str, Any]] = None,
    cloudflare_data: Optional[Dict[str, Any]] = None,
    request_log_id: Optional[int] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Process incoming WhatsApp message through Dify and send response via Twilio"""
    db = SessionLocal()
    start_time = datetime.utcnow()

    try:
        # Get or create conversation if not provided
        if not conversation_id:
            conversation_id = dify_service.get_conversation_id(from_number)

        # Get response from Dify
        dify_response = dify_service.send_message(
            user=from_number,
            message=body,
            conversation_id=conversation_id
        )

        # Get available number for response
        response_number = load_balancer.get_available_number()
        if not response_number:
            raise Exception("No available WhatsApp numbers")

        # Send response via Twilio
        twilio_response = twilio_client.send_message(
            to=from_number,
            body=dify_response["message"],
            from_number=response_number
        )

        if not twilio_response:
            raise Exception("Failed to send Twilio message")

        # Log successful message
        message_log = MessageLog(
            message_sid=message_sid,
            from_number=from_number,
            to_number=to_number,
            message=body,
            response=dify_response["message"],
            conversation_id=conversation_id,
            media_data=media_data,
            processing_time=(datetime.utcnow() - start_time).total_seconds()
        )
        db.add(message_log)
        db.commit()

        return {
            "status": "success",
            "message_sid": message_sid,
            "response_sid": twilio_response.get("sid")
        }

    except Exception as e:
        # Log error
        error_log = ErrorLog(
            error_type=type(e).__name__,
            error_message=str(e),
            error_metadata={
                "message_sid": message_sid,
                "from_number": from_number,
                "conversation_id": conversation_id
            }
        )
        db.add(error_log)
        db.commit()

        logger.error(
            "message_processing_error",
            error=str(e),
            message_sid=message_sid
        )

        raise e

    finally:
        db.close()

# Update celery app configuration
celery_app.conf.task_routes = {
    'process_message': {'queue': 'high'}
}