from celery import Celery
from core.config import settings
import logging
from services import ChatService, MessagingService, EcitzenAuthService
from utils.redis_pool import get_redis_client
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Celery app
celery_app = Celery('tasks',
                   broker=settings.CELERY_BROKER_URL,
                   backend=settings.CELERY_RESULT_BACKEND)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)


@celery_app.task(bind=True, max_retries=3)
def process_message(self, phone_number: str, message_body: str):
    logger.info(f"Processing message from {phone_number}: {message_body}")
    try:
        chat_service = ChatService()
        messaging_service = MessagingService()

        # Get or create a conversation
        conversation_id = chat_service.get_conversation_id(phone_number)

        # Generate a response using Dify
        response = chat_service.create_chat_message(phone_number, message_body, conversation_id)

        # Send the response back to the user via Twilio
        messaging_service.send_message(phone_number, response)

        logger.info(f"Successfully processed and responded to message from {phone_number}")
    except Exception as e:
        logger.error(f"Error processing message from {phone_number}: {str(e)}")
        # Retry task with exponential backoff
        retry_in = (self.request.retries + 1) * 60  # 60s, 120s, 180s
        raise self.retry(exc=e, countdown=retry_in)


@celery_app.task(bind=True, max_retries=3)
def check_phone(self, phone_number: str):
    logger.info(f"Checking phone number: {phone_number}")
    try:
        auth_service = EcitzenAuthService()
        user = auth_service.get_user_by_phone_or_username(phone_number)
        if user:
            user_response = auth_service.format_user_response(user)
            if not user.get('email'):
                auth_service.store_temp_data(phone_number, {
                    "phone_number": phone_number,
                    "user_id": user.get('id')
                })
                return {
                    "message": "User found but email not set",
                    "user": user_response,
                    "next_step": "check_email"
                }
            return {
                "message": "User found",
                "user": user_response
            }
        else:
            auth_service.store_temp_data(phone_number, {"phone_number": phone_number})
            return {"message": "User not found", "next_step": "check_email"}
    except Exception as e:
        logger.error(f"Error checking phone number {phone_number}: {str(e)}")
        # Retry task with exponential backoff
        retry_in = (self.request.retries + 1) * 60  # 60s, 120s, 180s
        raise self.retry(exc=e, countdown=retry_in)


@celery_app.task(bind=True, max_retries=3)
def check_email(self, phone_number: str, email: str):
    logger.info(f"Checking email for phone number: {phone_number}")
    try:
        auth_service = EcitzenAuthService()
        phone_user = auth_service.get_user_by_phone_or_username(phone_number)
        email_user = auth_service.get_user_by_email_or_username(email)

        if phone_user and email_user:
            # Both users exist - we need to merge them
            result = auth_service.merge_accounts(email_user, phone_user, email, phone_number)
            return {
                "message": "Accounts merged successfully",
                "user": auth_service.format_user_response(result)
            }
        elif phone_user:
            result = auth_service.add_email_to_user(phone_user, email)
            return {
                "message": "Email added to existing account",
                "user": auth_service.format_user_response(result)
            }
        elif email_user:
            result = auth_service.add_phone_to_user(email_user, phone_number)
            return {
                "message": "Phone attributes added to existing account",
                "user": auth_service.format_user_response(email_user)
            }
        else:
            return {"message": "User not found", "next_step": "create_account"}

    except Exception as e:
        logger.error(f"Error checking email for phone number {phone_number}: {str(e)}")
        retry_in = (self.request.retries + 1) * 60  # 60s, 120s, 180s
        raise self.retry(exc=e, countdown=retry_in)


@celery_app.task(bind=True, max_retries=3)
def create_account(self, phone_number: str, email: str, first_name: str, last_name: str, gender: str, country: str):
    logger.info(f"Creating account for phone number: {phone_number}")
    try:
        auth_service = EcitzenAuthService()
        temp_data = auth_service.get_temp_data(phone_number)
        if not temp_data:
            raise Exception("Invalid request sequence")

        result = auth_service.create_user_with_phone(
            phone_number=phone_number,
            email=email,
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            country=country,
            phone_type=temp_data.get("phoneType", "whatsapp"),
            phone_verified=temp_data.get("phoneVerified", "yes"),
            verification_route=temp_data.get("verificationRoute", "ngpt_wa")
        )
        auth_service.delete_temp_data(phone_number)
        return {
            "message": "User account created with UPDATE_PASSWORD action",
            "user_id": result["user_id"],
            "next_step": "verify_email"
        }
    except Exception as e:
        logger.error(f"Error creating account for phone number {phone_number}: {str(e)}")
        # Retry task with exponential backoff
        retry_in = (self.request.retries + 1) * 60  # 60s, 120s, 180s
        raise self.retry(exc=e, countdown=retry_in)


@celery_app.task(bind=True, max_retries=3)
def send_otp_email_task(self, email: str):
    logger.info(f"Sending OTP email to: {email}")
    try:
        otp = generate_otp()
        store_otp(email, otp)
        if send_otp_email(email, otp):
            return {"message": "OTP sent successfully"}
        else:
            logger.error(f"Failed to send OTP email to {email}")
            raise Exception("Failed to send OTP email")
    except Exception as e:
        logger.error(f"Error sending OTP email to {email}: {str(e)}")
        # Retry task with exponential backoff
        retry_in = (self.request.retries + 1) * 60  # 60s, 120s, 180s
        raise self.retry(exc=e, countdown=retry_in)


@celery_app.task(bind=True, max_retries=3)
def verify_email_task(self, email: str, otp: str):
    logger.info(f"Verifying email: {email}")
    try:
        verification_result = verify_otp(email, otp)
        if not verification_result["valid"]:
            raise Exception(verification_result["message"])

        # If OTP is valid, mark the email as verified in Keycloak
        result = verify_email(email)
        return {"message": "Email verified successfully."}
    except Exception as e:
        logger.error(f"Error verifying email {email}: {str(e)}")
        # Retry task with exponential backoff
        retry_in = (self.request.retries + 1) * 60  # 60s, 120s, 180s
        raise self.retry(exc=e, countdown=retry_in)


# Configure periodic tasks
celery_app.conf.beat_schedule = {
    'cleanup-redis-data': {
        'task': 'tasks.celery_tasks.cleanup_redis_data',
        'schedule': 3600.0,  # Run every hour
    },
}