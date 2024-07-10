from fastapi import FastAPI, Form
from scheduler.tasks import process_question

app = FastAPI()

@app.post("/message")
def reply(Body: str = Form(), From: str = Form()):
    process_question.delay(Body, From)
    return {"status": "Task added"}