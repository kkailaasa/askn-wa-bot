# Dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create directory for SQLite database and logs
RUN mkdir -p /app/app_data && \
    chmod 777 /app/app_data

# Add the current directory to PYTHONPATH
ENV PYTHONPATH=/app:${PYTHONPATH}

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8050"]