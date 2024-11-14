#!/bin/bash
set -e

# Wait for database to be ready
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "db" -U "postgres" -c '\q'; do
    >&2 echo "Postgres is unavailable - sleeping"
    sleep 1
done

>&2 echo "Postgres is up - executing command"

# Only run migrations from the web service
if [ "$SERVICE_NAME" = "web" ]; then
    echo "Running migrations..."
    alembic upgrade head
fi

# Run the command as appuser
exec gosu appuser "$@"