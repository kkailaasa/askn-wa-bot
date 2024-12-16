#!/bin/bash
set -e

# Create required directories with proper structure
mkdir -p /app/data/sqlite
mkdir -p /app/logs
mkdir -p /app/temp
mkdir -p /app/migrations
mkdir -p /app/celery

# Create celery schedule directory and file
touch /app/celery/celerybeat-schedule

# Set proper permissions for directories and files
chown -R appuser:appuser /app/data /app/logs /app/temp /app/migrations /app/celery
chmod -R 775 /app/data /app/logs /app/temp /app/migrations /app/celery

# Initialize and run migrations only from web service
if [ "$SERVICE_NAME" = "web" ]; then
    echo "Checking migrations..."

    # Set proper DB_PATH if not provided
    DB_PATH=${DB_PATH:-"/app/data/sqlite/app.db"}

    # Create database directory if it doesn't exist
    DB_DIR=$(dirname "$DB_PATH")
    mkdir -p "$DB_DIR"

    # Create database file if it doesn't exist and set permissions
    touch "$DB_PATH"
    chown appuser:appuser "$DB_PATH"
    chmod 664 "$DB_PATH"

    # Initialize alembic if not already initialized
    if [ ! -f "/app/migrations/env.py" ]; then
        echo "Initializing alembic..."
        gosu appuser alembic init migrations
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