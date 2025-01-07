# tasks.py
from celery import Celery
from dify_client import ChatClient
from decouple import config
from app.tasks.utils import send_message, logger, is_rate_limited, log_message

app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

@app.task
def process_question(Body: str, From: str):
    logger.info("Processing new message")
    dify_key = config("DIFY_KEY")
    chat_client = ChatClient(dify_key)

    try:
        if is_rate_limited(From):
            logger.info(f"Rate limit exceeded for {From}")
            send_message(From, "You have exceeded the message rate limit. Please try again later.")
            return

        chat_client.base_url = config('DIFY_BASE_URL')

        # Rest of the code remains the same...