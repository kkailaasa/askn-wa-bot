#!/bin/bash
# Start the web server in the background
uvicorn main:app --host 0.0.0.0 --port 8000 &

# Start the Celery worker in the background
celery -A scheduler.tasks worker --loglevel=info &

# Start the Celery beat scheduler in the background
celery -A scheduler.tasks beat --loglevel=info &

# Wait for all background processes to finish
wait
