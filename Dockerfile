FROM python:3.11-slim

# Install gosu and other dependencies
RUN set -eux; \
    apt-get update; \
    apt-get install -y gosu sqlite3; \
    rm -rf /var/lib/apt/lists/*; \
    gosu nobody true

# Set the working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create required directories with proper permissions
RUN mkdir -p /app/data /app/logs /app/temp /app/templates /app/migrations \
    && chown -R root:root /app \
    && chmod -R 755 /app \
    && chmod -R 777 /app/data  # Ensure SQLite has write permissions

# Copy entrypoint script first and make it executable 
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Copy the rest of the application
COPY . .

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app/logs /app/temp /app/templates /app/migrations \
    && chown -R appuser:appuser /app/data

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PATH="/usr/local/bin:$PATH"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]