#!/bin/bash
set -e

# Create required directories
mkdir -p /app/data/sqlite
mkdir -p /app/logs
mkdir -p /app/temp
mkdir -p /app/migrations
mkdir -p /app/celery

# Create celery schedule directory and file
touch /app/celery/celerybeat-schedule

# Set proper permissions
chown -R appuser:appuser /app/data /app/logs /app/temp /app/migrations /app/celery
chmod -R 775 /app/data /app/logs /app/temp /app/migrations /app/celery

# Initialize and run migrations only from web service
if [ "$SERVICE_NAME" = "web" ]; then
    echo "Checking migrations..."
    
    # Create database file with proper permissions
    touch /app/data/sqlite/app.db
    chown appuser:appuser /app/data/sqlite/app.db
    chmod 664 /app/data/sqlite/app.db

    # Initialize alembic if not already initialized
    if [ ! -f "/app/migrations/env.py" ]; then
        echo "Initializing alembic..."
        gosu appuser alembic init -t async /app/migrations
    fi

    # Run migrations
    echo "Running migrations..."
    gosu appuser alembic upgrade head || {
        echo "Creating initial migration..."
        gosu appuser alembic revision --autogenerate -m "Initial migration"
        gosu appuser alembic upgrade head
    }
fi

# Run the command as appuser
exec gosu appuser "$@"