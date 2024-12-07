# app/worker/celery_app.py

from celery import Celery
from app.core.config import settings

# Initialize Celery with Redis broker
celery_app = Celery(
    "worker",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task settings
    task_acks_late=True,  # Tasks are acknowledged after execution
    task_reject_on_worker_lost=True,  # Tasks are rejected if worker disconnects
    # Queue settings
    task_queues={
        'high': {'routing_key': 'high'},
        'default': {'routing_key': 'default'},
        'low': {'routing_key': 'low'}
    },
    # Retry settings
    task_retry_delay_start=1,  # Start with 1 second delay
    task_max_retries=3,  # Maximum number of retries
    # Rate limiting
    task_default_rate_limit='100/s',  # Default rate limit per worker
    # Error handling
    task_annotations={
        '*': {
            'rate_limit': '100/s',
            'retry_backoff': True,
            'retry_backoff_max': 600,  # Maximum retry delay of 10 minutes
            'retry_jitter': True  # Add randomness to retry delays
        }
    }
)