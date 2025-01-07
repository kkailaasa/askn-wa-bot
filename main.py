from fastapi import FastAPI, Form, HTTPException
from typing import Optional
from app.scheduler.tasks import process_question
from app.db.database import init_db
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

@app.post("/message")
async def reply(
    MessageSid: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    Body: Optional[str] = Form(None),
    NumMedia: Optional[str] = Form("0"),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
    WaId: Optional[str] = Form(None),
    ProfileName: Optional[str] = Form(None)
):
    try:
        # Log incoming request details
        logger.info(f"Received webhook - MessageSid: {MessageSid}, From: {From}, To: {To}")

        # Validate required fields
        if not Body:
            logger.warning(f"Missing Body in request from {From}")
            raise HTTPException(
                status_code=422,
                detail="Message body is required"
            )

        if not From:
            logger.warning("Missing From field in request")
            raise HTTPException(
                status_code=422,
                detail="From field is required"
            )

        # Clean and validate the phone number
        From = From.strip()
        if not From.startswith("whatsapp:"):
            From = f"whatsapp:{From}"

        # Handle media messages
        media_info = {}
        if NumMedia and int(NumMedia) > 0:
            media_info = {
                "url": MediaUrl0,
                "content_type": MediaContentType0
            }
            logger.info(f"Media received from {From}: {media_info}")

        # Log message details
        logger.info(f"Processing message - From: {From}, ProfileName: {ProfileName}, Body: {Body}")
        if WaId:
            logger.info(f"WhatsApp ID: {WaId}")

        # Process the message
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
            "message": "Message received and queued for processing",
            "message_sid": MessageSid
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )