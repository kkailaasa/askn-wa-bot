from fastapi import APIRouter, Form
from tasks.celery_tasks import process_question

router = APIRouter()

@router.post("/message")
def reply(Body: str = Form(), From: str = Form()):
    process_question.delay(Body, From)
    return {"status": "Task added"}