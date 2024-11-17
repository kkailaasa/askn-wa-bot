FROM python:3.10-slim

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

# Copy the rest of the application
COPY . .

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser

# Set ownership for application directories
RUN chown -R appuser:appuser /app \
    && chmod +x /usr/local/bin/entrypoint.sh

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Copy and set up entrypoint
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default command (will be overridden by docker-compose for celery services)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]