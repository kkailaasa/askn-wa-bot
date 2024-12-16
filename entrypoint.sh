#!/bin/bash
set -e

# Create required directories if they don't exist
mkdir -p /app/data
mkdir -p /app/logs
mkdir -p /app/temp
mkdir -p /app/migrations

# Set proper permissions
chown -R appuser:appuser /app/data /app/logs /app/temp /app/migrations
chmod -R 777 /app/data  # Ensure SQLite has write permissions

# Initialize and run migrations only from web service
if [ "$SERVICE_NAME" = "web" ]; then
    echo "Checking migrations..."

    # Create SQLite database directory with proper permissions
    mkdir -p $(dirname $DB_PATH)
    touch $DB_PATH
    chown appuser:appuser $DB_PATH
    chmod 666 $DB_PATH

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