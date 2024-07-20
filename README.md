# prerequisites
- python3
- git
- redis
- tmux
Redis-server is used for caching the user login, conversation id, and rate limiting. It is also used by celery as broker.

# commands to run
commands need to run from the project_root_folder
- after cloning the progect create a python venv
- then install all the libraries from requirements.txt
- then run the uvicorn command `uvicorn main:app --host 0.0.0.0 --port 8000`
to run it in detached mode you can use nohup at the begining of the command and & at the end
- then run the celery command `celery -A scheduler.tasks worker --loglevel=info`
to run this in detached mode you can use nohup at the begining of the command and & at the end

## Deploying with Docker

Follow these steps to deploy the application using Docker:

0. Clone the Git repository:
    ```bash
    git clone <repository-url>
    ```

1. Update your `.env` file with the necessary environment variables.

2. Build the Docker image:
    ```bash
    docker build -t an-wa-bot:v1 .
    ```

3. Run Docker Compose:
    ```bash
    docker compose up -d
    ```

4. Check the logs to ensure everything is running correctly:
    ```bash
    docker compose logs -f
    ```

5. Configure your reverse proxy according to your setup.

6. Configure Cloudflare as needed for your deployment.
