# eCitizen Registration Integration with NGPT System

## Overview
This project implements an eCitizen registration system for WhatsApp users, modified from the main repo to be used by the NGPT Backend Service. It provides a set of API endpoints for user registration, email verification, and message handling.

## Key Features
- User registration via WhatsApp
- Email verification with OTP
- Integration with Twilio for WhatsApp messaging
- Asynchronous message processing using Celery
- Rate limiting to prevent abuse
- Redis-based data caching and temporary storage

## Documentation
Refer to the following files for specific Documentation:

- **API Endpoints**: For a comprehensive list and description of all API endpoints, see `api_endpoints_reference.md`.
- **Registration Flow**: To understand the eCitizen registration process, refer to `ecitizen_registration_flow.md`.
- **Version History and Functionalities**: For information about the project's version history and implemented functionalities, see `Version_Control.md`.

## Setup for Development
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables as specified in `.env.example`
4. Run Redis server
5. Start Celery worker: `celery -A tasks.celery_tasks worker --loglevel=info`
6. Start Celery beat: `celery -A tasks.celery_tasks beat --loglevel=info`
7. Run the FastAPI server: `uvicorn main:app --host 0.0.0.0 --port 8000`

## Docker Deployment
A `Dockerfile` and `docker-compose.yml` are provided for easy deployment. Set your `.env` file and Use `docker-compose up` to start all services.
