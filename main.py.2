from fastapi import FastAPI, Form, HTTPException
from typing import Optional
from app.scheduler.tasks import process_question
from app.db.database import init_db

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    init_db()

@app.post("/message")
async def reply(
    Body: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
):
    # Validate required fields
    if not Body or not From:
        raise HTTPException(
            status_code=422,
            detail="Both 'Body' and 'From' fields are required"
        )

    # Clean the phone number
    From = From.strip()
    if not From.startswith("whatsapp:"):
        From = f"whatsapp:{From}"

    # Log the incoming message
    print(f"Received message from {From}: {Body}")

    # Process the message
    process_question.delay(Body, From)

    # Return a simple acknowledgment
    return {"status": "Message received", "message": "Task added to queue"}