# main.py
from fastapi import FastAPI, Form
from app.scheduler.tasks import process_question
from app.db.database import init_db

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    init_db()  # Create database tables on startup

@app.post("/message")
def reply(Body: str = Form(), From: str = Form()):
    print("twilio has been called")
    process_question.delay(Body, From)
    return {"status": "Task added"}