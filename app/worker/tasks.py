# app/worker/tasks.py

import asyncio
import nest_asyncio
from celery import shared_task
from app.worker.celery_app import celery_app
from app.services.dify import DifyService, DifyError
from app.services.twilio import TwilioClient
from app.services.load_balancer import LoadBalancer
from app.db.database import SessionLocal
from app.db.models import MessageLog, ErrorLog
import structlog
from datetime import datetime
from typing import Optional, Dict, Any

# Enable nested event loops
nest_asyncio.apply()

logger = structlog.get_logger()

# Initialize services
dify_service = DifyService()
twilio_client = TwilioClient()
load_balancer = LoadBalancer()

class MessageProcessingError(Exception):
    """Custom exception for message processing errors"""
    pass

@shared_task(
    name="process_message",
    queue="high",
    max_retries=3,
    autoretry_for=(MessageProcessingError,),
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
    """Process incoming WhatsApp message"""

    db = SessionLocal()
    start_time = datetime.utcnow()

    async def process_operations():
        """Handle all async operations"""
        nonlocal conversation_id

        try:
            # Get conversation ID if not provided
            if not conversation_id:
                conv_id = await dify_service.get_conversation_id(from_number)
                if not conv_id:
                    logger.error(
                        "conversation_creation_failed",
                        from_number=from_number
                    )
                    raise MessageProcessingError("Could not create conversation")
                conversation_id = conv_id

            # Get response from Dify
            dify_response = await dify_service.send_message(
                user=from_number,
                message=body,
                conversation_id=conversation_id
            )

            if not dify_response or "message" not in dify_response:
                raise MessageProcessingError("Invalid Dify response")

            # Get available number for response
            response_number = await load_balancer.get_available_number()
            if not response_number:
                raise MessageProcessingError("No available numbers")

            # Send response via Twilio
            twilio_response = await twilio_client.send_message(
                to=from_number,
                body=dify_response["message"],
                from_number=response_number
            )

            if not twilio_response:
                raise MessageProcessingError("Failed to send response")

            return dify_response, twilio_response

        except Exception as e:
            logger.error("process_error", error=str(e))
            raise MessageProcessingError(f"Processing error: {str(e)}")

    try:
        # Create new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run async operations
        dify_response, twilio_response = loop.run_until_complete(process_operations())

        # Log successful message
        message_log = MessageLog(
            message_sid=message_sid,
            from_number=from_number,
            to_number=to_number,
            message=body,
            response=dify_response.get("message", ""),
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
        logger.error(
            "message_processing_error",
            error=str(e),
            message_sid=message_sid
        )

        try:
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
        except Exception as db_error:
            logger.error(
                "error_logging_failed",
                error=str(db_error),
                original_error=str(e)
            )

        raise MessageProcessingError(str(e))

    finally:
        db.close()
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except Exception as e:
            logger.error("loop_cleanup_error", error=str(e))