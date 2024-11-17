FROM python:3.11-slim

# Install gosu, postgres client and other dependencies
RUN set -eux; \
    apt-get update; \
    apt-get install -y gosu postgresql-client ; \
    rm -rf /var/lib/apt/lists/*; \
    gosu nobody true

# Set the working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create required directories
RUN mkdir -p logs temp templates

# Copy entrypoint script first and make it executable
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Copy the rest of the application
COPY . .

# Create a non-root user and set ownership
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default command (will be overridden by docker-compose for celery services)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]