#!/bin/bash
set -e

# Create required directories
mkdir -p /app/data
mkdir -p /app/logs
mkdir -p /app/temp
mkdir -p /app/migrations

# Set proper permissions for directories
chown -R appuser:appuser /app/data
chown -R appuser:appuser /app/logs
chown -R appuser:appuser /app/temp
chown -R appuser:appuser /app/migrations
chmod -R 775 /app/data
chmod -R 775 /app/logs
chmod -R 775 /app/temp
chmod -R 775 /app/migrations

# Create and set permissions for Celery Beat schedule file
touch /app/celerybeat-schedule
chown appuser:appuser /app/celerybeat-schedule
chmod 664 /app/celerybeat-schedule

# Initialize and run migrations only from web service
if [ "$SERVICE_NAME" = "web" ]; then
    echo "Checking migrations..."

    # Create SQLite database directory with proper permissions
    DB_DIR=$(dirname "$DB_PATH")
    mkdir -p "$DB_DIR"
    touch "$DB_PATH"
    chown -R appuser:appuser "$DB_DIR"
    chmod 775 "$DB_DIR"
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