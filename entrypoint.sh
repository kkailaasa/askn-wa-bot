#!/bin/bash
set -e

# Create required directories
mkdir -p /app/data    # For SQLite database
mkdir -p /app/logs
mkdir -p /app/temp
mkdir -p /app/migrations

# Set proper permissions
chown -R appuser:appuser /app/data /app/logs /app/temp /app/migrations

# Initialize and run migrations only from web service
if [ "$SERVICE_NAME" = "web" ]; then
    echo "Checking migrations..."

    # Initialize alembic if not already initialized
    if [ ! -f "/app/migrations/env.py" ]; then
        echo "Initializing alembic..."
        gosu appuser alembic init migrations
    fi

    # Run migrations
    echo "Running migrations..."
    gosu appuser alembic upgrade head || gosu appuser alembic revision --autogenerate -m "Initial migration"
fi

# Run the command as appuser
exec gosu appuser "$@"