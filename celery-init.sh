#!/bin/bash
# Initialize celery beat schedule

# Create directory if it doesn't exist
mkdir -p /app/celery

# Create an empty shelve database
python3 -c '
import shelve
with shelve.open("/app/celery/celerybeat-schedule", "c") as db:
    db["entries"] = {}  # Initialize empty entries
    db["__version__"] = 1
'

# Set proper permissions
chown -R appuser:appuser /app/celery
chmod -R 775 /app/celery
chmod 664 /app/celery/celerybeat-schedule*