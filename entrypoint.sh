#!/bin/bash
set -e

# Create required directories if they don't exist
mkdir -p /app/data  # For SQLite database
mkdir -p /app/logs
mkdir -p /app/temp
mkdir -p /app/templates

# Set proper permissions
chown -R appuser:appuser /app/data /app/logs /app/temp /app/templates

# Only run migrations from the web service
if [ "$SERVICE_NAME" = "web" ]; then
    echo "Running migrations..."
    gosu appuser alembic upgrade head
fi

# Run the command as appuser
exec gosu appuser "$@"