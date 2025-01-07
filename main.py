from fastapi import FastAPI, Form, HTTPException
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
async def reply(
    Body: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
    MessageSid: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    MessageStatus: Optional[str] = Form(None),
    SmsStatus: Optional[str] = Form(None),
    NumMedia: Optional[str] = Form("0"),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
    WaId: Optional[str] = Form(None),
    ProfileName: Optional[str] = Form(None),
    **kwargs  # This will catch additional media URLs if present
):
    try:
        # Log basic request info
        logger.info(f"Received webhook - From: {From}, To: {To}, MessageSid: {MessageSid}")

        # Handle status updates
        if MessageStatus or SmsStatus:
            status = MessageStatus or SmsStatus
            logger.info(f"Status update received: {status}")
            return {
                "status": "success",
                "type": "status_update",
                "message": f"Status update ({status}) received"
            }

        # Clean the phone number if present
        if From:
            From = From.strip()
            if not From.startswith("whatsapp:"):
                From = f"whatsapp:{From}"

        # Handle media messages
        if NumMedia and int(NumMedia) > 0:
            logger.info(f"Media message received - Count: {NumMedia}")

            # Collect all media URLs and types
            media_items = []
            num_media = int(NumMedia)

            # Get all media URLs from the form data
            for i in range(num_media):
                url_key = f"MediaUrl{i}"
                content_type_key = f"MediaContentType{i}"

                url = kwargs.get(url_key, None) if i > 0 else MediaUrl0
                content_type = kwargs.get(content_type_key, None) if i > 0 else MediaContentType0

                if url and content_type:
                    media_items.append({
                        "url": url,
                        "content_type": content_type,
                        "index": i
                    })
                    logger.info(f"Media {i}: Type: {content_type}, URL: {url}")

            # If we have a body message along with media, include it
            message_text = Body if Body else "Image message"

            # Queue the message processing with media information
            try:
                process_question.delay(message_text, From, media_items)
                logger.info(f"Task queued successfully for {From} with {len(media_items)} media items")

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
        elif Body and From:
            # Log message details
            logger.info(f"Processing text message - From: {From}, ProfileName: {ProfileName}, Body: {Body}")
            if WaId:
                logger.info(f"WhatsApp ID: {WaId}")

            # Queue message for processing
            try:
                process_question.delay(Body, From)
                logger.info(f"Task queued successfully for {From}")

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

        # If we get here, it's a webhook with insufficient data
        logger.warning("Received webhook with insufficient data")
        return {
            "status": "error",
            "type": "unknown",
            "message": "Insufficient data in webhook"
        }

    except HTTPException:
        raise
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
    uvicorn.run(app, host="0.0.0.0", port=8050)