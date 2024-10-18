from celery import Celery
from core.config import settings
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Celery app
app = Celery('tasks', broker=settings.REDIS_URL, backend=settings.REDIS_URL)

app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

@app.task
def process_question(Body: str, From: str):
    # Your existing task code here
    logger.info(f"Processing question: {Body} from {From}")
    # Add your processing logic here

@app.task
def cleanup_redis_data():
    logger.info("Starting Redis data cleanup task")
    # Add your cleanup logic here

# Update Celery beat schedule
app.conf.beat_schedule = {
    'cleanup-redis-data': {
        'task': 'tasks.celery_tasks.cleanup_redis_data',
        'schedule': 3600.0,  # Run every hour
    },
}

if __name__ == '__main__':
    app.start()