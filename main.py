from fastapi import FastAPI, Form, HTTPException, Request
from typing import Optional
from app.scheduler.tasks import process_question
from app.db.database import init_db
import logging
from datetime import datetime

# Configure logging with timestamp
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app_data/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="WhatsApp Bot API")

@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

@app.get("/")
async def root():
    return {
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.post("/message")
async def reply(request: Request):
    try:
        # Get form data
        form = await request.form()

        # Log all incoming data for debugging
        logger.info("Received webhook data:")
        for key, value in form.items():
            logger.info(f"{key}: {value}")

        # Extract fields with defaults
        message_sid = form.get('MessageSid', '')
        body = form.get('Body', '')
        from_number = form.get('From', '')
        to_number = form.get('To', '')
        num_media = form.get('NumMedia', '0')
        message_status = form.get('MessageStatus', '')
        sms_status = form.get('SmsStatus', '')
        message_type = form.get('MessageType', '')

        # Log basic request info
        logger.info(f"Received webhook - MessageSid: {message_sid}, From: {from_number}, To: {to_number}")

        # Handle status updates - only for specific status types
        if message_status in ['sent', 'delivered', 'read', 'failed'] or sms_status in ['sent', 'delivered', 'read', 'failed']:
            status = message_status or sms_status
            logger.info(f"Status update received: {status}")
            return {
                "status": "success",
                "type": "status_update",
                "message": f"Status update ({status}) received"
            }

        # Process incoming messages
        if message_type == 'text' or body or int(num_media) > 0:
            # Validate From number
            if not from_number:
                logger.error("Missing From number")
                return {
                    "status": "error",
                    "message": "Missing From number"
                }

            # Clean the phone number
            from_number = from_number.strip()
            if not from_number.startswith("whatsapp:"):
                from_number = f"whatsapp:{from_number}"

            # Handle media messages
            media_items = []
            if num_media and int(num_media) > 0:
                num_media_int = int(num_media)
                logger.info(f"Media message received - Count: {num_media_int}")

                # Collect all media URLs and types
                for i in range(num_media_int):
                    url = form.get(f'MediaUrl{i}')
                    content_type = form.get(f'MediaContentType{i}')

                    if url and content_type:
                        media_items.append({
                            "url": url,
                            "content_type": content_type,
                            "index": i
                        })
                        logger.info(f"Media {i}: Type: {content_type}, URL: {url}")

                message_text = body if body else "Image message"
                try:
                    process_question.delay(message_text, from_number, media_items)
                    logger.info(f"Task queued successfully for {from_number} with {len(media_items)} media items")
                    return {
                        "status": "success",
                        "message": "Message with media received and queued for processing"
                    }
                except Exception as e:
                    logger.error(f"Failed to queue media task: {str(e)}")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to process media message"
                    )

            # Handle text-only messages
            elif body:
                logger.info(f"Processing text message - From: {from_number}, Body: {body}")

                try:
                    process_question.delay(body, from_number)
                    logger.info(f"Task queued successfully for {from_number}")
                    return {
                        "status": "success",
                        "message": "Message received and queued for processing"
                    }
                except Exception as e:
                    logger.error(f"Failed to queue task: {str(e)}")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to process message"
                    )

        # Handle other types of webhooks
        logger.warning("Received webhook with no message content")
        return {
            "status": "success",
            "type": "unknown",
            "message": "Webhook received but no message content found"
        }

    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)