# app/worker/tasks.py

from app.worker.celery_app import celery_app
from app.services.dify import DifyService
from app.services.twilio import TwilioClient
from app.services.load_balancer import LoadBalancer
from app.db.database import SessionLocal
from app.db.models import MessageLog, ErrorLog
import structlog
from datetime import datetime

logger = structlog.get_logger()
dify_service = DifyService()
twilio_client = TwilioClient()
load_balancer = LoadBalancer()

@celery_app.task(
    bind=True,
    name="process_message",
    queue="high",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True
)
def process_message(
    self,
    message_sid: str,
    from_number: str,
    to_number: str,
    body: str,
    conversation_id: str = None,
    media_data: dict = None
):
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

        # Get available Twilio number for response
        response_number = load_balancer.get_available_number()

        # Send response via Twilio
        twilio_response = twilio_client.send_message(
            from_=response_number,
            to=from_number,
            body=dify_response["message"]
        )

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
            metadata={
                "message_sid": message_sid,
                "from_number": from_number,
                "conversation_id": conversation_id,
                "retry_count": self.request.retries
            }
        )
        db.add(error_log)
        db.commit()

        logger.error(
            "message_processing_error",
            error=str(e),
            message_sid=message_sid,
            retry_count=self.request.retries
        )

        # Retry with exponential backoff if not max retries
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        raise e

    finally:
        db.close()

@celery_app.task(
    bind=True,
    name="cleanup_old_messages",
    queue="low"
)
def cleanup_old_messages(self, days_old: int = 30):
    """Cleanup old message logs"""
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        db.query(MessageLog).filter(
            MessageLog.timestamp < cutoff_date
        ).delete()
        db.commit()
    except Exception as e:
        logger.error("cleanup_error", error=str(e))
        raise
    finally:
        db.close()