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
