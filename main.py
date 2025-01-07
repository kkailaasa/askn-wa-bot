from fastapi import FastAPI, Form, HTTPException
from typing import Optional
from app.scheduler.tasks import process_question
from app.db.database import init_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    init_db()

@app.post("/message")
async def reply(
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: Optional[str] = Form(None),
    MessageStatus: Optional[str] = Form(None),
    SmsStatus: Optional[str] = Form(None),
    NumMedia: Optional[str] = Form("0"),
    WaId: Optional[str] = Form(None)
):
    # If it's a status update, just log and return
    if MessageStatus or SmsStatus:
        logger.info(f"Status update for {MessageSid}: {MessageStatus or SmsStatus}")
        return {"status": "success", "message": "Status update received"}

    # If it's a message, proceed with normal processing
    if Body:
        From = From.strip()
        if not From.startswith("whatsapp:"):
            From = f"whatsapp:{From}"

        logger.info(f"Received message from {From}: {Body}")
        process_question.delay(Body, From)
        return {"status": "success", "message": "Message queued for processing"}

    # If neither status nor body, something's wrong
    logger.warning(f"Received webhook with no status or body for {MessageSid}")
    return {"status": "success", "message": "Webhook received but no action taken"}