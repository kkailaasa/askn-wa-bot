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
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: Optional[str] = Form(None),
    MessageStatus: Optional[str] = Form(None),
    SmsStatus: Optional[str] = Form(None),
    NumMedia: Optional[str] = Form("0"),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
    WaId: Optional[str] = Form(None),
    ProfileName: Optional[str] = Form(None)
):
    try:
        # Log basic request info
        logger.info(f"Received webhook - MessageSid: {MessageSid}, From: {From}, To: {To}")

        # Handle status updates
        if MessageStatus or SmsStatus:
            status = MessageStatus or SmsStatus
            logger.info(f"Status update for {MessageSid}: {status}")
            return {
                "status": "success",
                "type": "status_update",
                "message": f"Status update ({status}) received"
            }

        # Handle media messages
        if NumMedia and int(NumMedia) > 0:
            logger.info(f"Media message received - Type: {MediaContentType0}, URL: {MediaUrl0}")
            # You can add specific media handling here if needed

        # Handle text messages
        if Body:
            # Clean the phone number
            From = From.strip()
            if not From.startswith("whatsapp:"):
                From = f"whatsapp:{From}"

            # Log message details
            logger.info(f"Processing message - From: {From}, ProfileName: {ProfileName}, Body: {Body}")
            if WaId:
                logger.info(f"WhatsApp ID: {WaId}")

            # Queue message for processing
            try:
                process_question.delay(Body, From)
                logger.info(f"Task queued successfully for {From}")
            except Exception as e:
                logger.error(f"Failed to queue task: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to process message"
                )

            return {
                "status": "success",
                "type": "message",
                "message": "Message received and queued for processing",
                "message_sid": MessageSid
            }

        # If we get here, it's a webhook with no status or body
        logger.warning(f"Received webhook with no status or body for {MessageSid}")
        return {
            "status": "success",
            "type": "unknown",
            "message": "Webhook received but no action taken"
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