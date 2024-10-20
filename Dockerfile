FROM python:3.10-slim

# Install gosu, libmagic, and its development files
RUN set -eux; \
    apt-get update; \
    apt-get install -y gosu libmagic1 libmagic-dev; \
    rm -rf /var/lib/apt/lists/*; \
    # verify that the binary works
    gosu nobody true

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser

# Set the working directory ownership
RUN chown -R appuser:appuser /app

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable
ENV PYTHONUNBUFFERED=1

# Use gosu to drop privileges and run the command
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Run app.py when the container launches
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]