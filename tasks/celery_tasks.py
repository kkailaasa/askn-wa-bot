from celery import Celery, Task
from kombu import Queue
from core.config import settings
import structlog
from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime
from core.sequence_errors import SequenceException, SequenceErrorCode
from services import (
    ChatService,
    MessagingService,
    auth_service,
    sequence_manager,
    AccountCreationStep,
    email_service
)

from utils.redis_pool import get_redis_client
from celery.signals import (
    task_prerun,
    task_postrun,
    task_retry,
    task_failure,
    task_success,
    worker_ready,
    worker_shutdown
)

logger = structlog.get_logger(__name__)
redis_client = get_redis_client()

class BaseTaskWithRetry(Task):
    autoretry_for = (Exception,)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log retry attempts"""
        logger.warning(
            "task_retry",
            task_id=task_id,
            task_name=self.name,
            exc_info=str(exc),
            attempt=self.request.retries + 1,
            args=args,
            kwargs=kwargs
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failures"""
        logger.error(
            "task_failure",
            task_id=task_id,
            task_name=self.name,
            exc_info=str(exc),
            args=args,
            kwargs=kwargs
        )

# Single Celery app initialization with all configurations
celery_app = Celery(
    'tasks',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Configure Celery using settings
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=settings.CELERY_ENABLE_UTC,
    task_track_started=settings.CELERY_TASK_TRACK_STARTED,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    worker_prefetch_multiplier=settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
    worker_max_tasks_per_child=settings.CELERY_WORKER_MAX_TASKS_PER_CHILD,
    worker_max_memory_per_child=settings.CELERY_WORKER_MAX_MEMORY_PER_CHILD,

    # Queue configuration
    task_queues=(
        Queue('high', routing_key='high'),
        Queue('default', routing_key='default'),
        Queue('low', routing_key='low'),
    ),

    task_default_queue='default',

    # Task routing
    task_routes={
        'tasks.celery_tasks.process_message': {'queue': 'high'},
        'tasks.celery_tasks.check_phone': {'queue': 'default'},
        'tasks.celery_tasks.check_email': {'queue': 'default'},
        'tasks.celery_tasks.create_account': {'queue': 'default'},
        'tasks.celery_tasks.send_otp_email_task': {'queue': 'high'},
        'tasks.celery_tasks.verify_email_task': {'queue': 'default'},
    }
)

# Signal handlers
@worker_ready.connect
def worker_ready_handler(**kwargs):
    logger.info("celery_worker_ready")

@worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    logger.info("celery_worker_shutting_down")

@task_prerun.connect
def task_prerun_handler(task_id, task, args, kwargs, **_):
    logger.info(
        "task_started",
        task_id=task_id,
        task_name=task.name,
        args=args,
        kwargs=kwargs
    )

@task_postrun.connect
def task_postrun_handler(task_id, task, args, kwargs, retval, state, **_):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logger.info(
        "task_completed",
        task_id=task_id,
        task_name=task.name,
        state=state
    )
    loop.close()

def run_async(coroutine):
    """Helper to run async code in sync context"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coroutine)
        loop.close()
        return result
    except Exception as e:
        if 'loop' in locals():
            loop.close()
        raise e

@celery_app.task(
    bind=True,
    base=BaseTaskWithRetry,
    queue='high',
    rate_limit='100/s'
)

def process_message(self, phone_number: str, message_body: str) -> Dict[str, Any]:
    """Process incoming messages with enhanced error handling"""
    logger.info("processing_message", phone_number=phone_number)

    try:
        chat_service = ChatService()
        messaging_service = MessagingService()

        # Handle "start new chat" command
        if message_body.lower().strip() == "start new chat":
            response = run_async(
                chat_service.create_chat_message(
                    phone_number=phone_number,
                    message=message_body,
                    conversation_id=None
                )
            )
        else:
            conversation_id = run_async(
                chat_service.get_conversation_id(phone_number)
            )
            response = run_async(
                chat_service.create_chat_message(
                    phone_number=phone_number,
                    message=message_body,
                    conversation_id=conversation_id
                )
            )

        # Send response message
        messaging_service.send_message(phone_number, response.get('message', ''))

        logger.info(
            "message_processed",
            phone_number=phone_number,
            conversation_id=response.get('conversation_id')
        )

        return {
            'status': 'success',
            'response': response,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(
            "message_processing_failed",
            phone_number=phone_number,
            error=str(e),
            error_type=type(e).__name__
        )
        raise self.retry(exc=e)

@celery_app.task(bind=True, base=BaseTaskWithRetry)
def check_phone(self, phone_number: str) -> Dict[str, Any]:
    """Check phone number with enhanced validation"""
    logger.info("checking_phone", phone_number=phone_number)

    try:
        # Validate and start sequence
        run_async(
            sequence_manager.validate_step(
                phone_number,
                AccountCreationStep.CHECK_PHONE
            )
        )

        # Check if user exists
        user = run_async(
            auth_service.get_user_by_email_or_username(None, phone_number)
        )

        # Store step data
        step_data = {
            "phone_number": phone_number,
            "verification_status": bool(user),
            "timestamp": datetime.utcnow().isoformat()
        }

        run_async(
            sequence_manager.store_step_data(
                phone_number,
                AccountCreationStep.CHECK_PHONE,
                step_data
            )
        )

        if user:
            if not user.get('email'):
                run_async(
                    sequence_manager.update_step(
                        phone_number,
                        AccountCreationStep.CHECK_EMAIL
                    )
                )
                return {
                    "message": "User found but email not set",
                    "user": user,
                    "next_step": "check_email"
                }
            return {
                "message": "User found",
                "user": user
            }

        run_async(
            sequence_manager.update_step(
                phone_number,
                AccountCreationStep.CHECK_EMAIL
            )
        )
        return {"message": "User not found", "next_step": "check_email"}

    except Exception as e:
        logger.error(
            "phone_check_failed",
            phone_number=phone_number,
            error=str(e)
        )
        raise self.retry(exc=e)

@celery_app.task(bind=True, base=BaseTaskWithRetry)
def check_email(self, phone_number: str, email: str) -> Dict[str, Any]:
    """Validate email with enhanced error handling"""
    logger.info(
        "checking_email",
        phone_number=phone_number,
        email=email
    )

    try:
        run_async(
            sequence_manager.validate_step(
                phone_number,
                AccountCreationStep.CHECK_EMAIL
            )
        )

        # Check existing users
        phone_user = run_async(
            auth_service.get_user_by_email_or_username(None, phone_number)
        )
        email_user = run_async(
            auth_service.get_user_by_email_or_username(None, email)
        )

        # Store verification data
        step_data = {
            "email": email,
            "phone_number": phone_number,
            "verification_status": bool(email_user),
            "timestamp": datetime.utcnow().isoformat()
        }

        run_async(
            sequence_manager.store_step_data(
                phone_number,
                AccountCreationStep.CHECK_EMAIL,
                step_data
            )
        )

        # Update sequence state
        run_async(
            sequence_manager.update_step(
                phone_number,
                AccountCreationStep.CREATE_ACCOUNT
            )
        )

        return {
            "message": "Email check completed",
            "next_step": "create_account",
            "existing_phone_user": bool(phone_user),
            "existing_email_user": bool(email_user)
        }

    except Exception as e:
        logger.error(
            "email_check_failed",
            phone_number=phone_number,
            email=email,
            error=str(e)
        )
        raise self.retry(exc=e)

@celery_app.task(bind=True, base=BaseTaskWithRetry)
def create_account(
    self,
    phone_number: str,
    email: str,
    first_name: str,
    last_name: str,
    gender: str,
    country: str
) -> Dict[str, Any]:
    """Create user account with enhanced validation"""
    logger.info(
        "creating_account",
        phone_number=phone_number,
        email=email
    )

    try:
        # Validate sequence step
        run_async(
            sequence_manager.validate_step(
                phone_number,
                AccountCreationStep.CREATE_ACCOUNT
            )
        )

        # Create account data
        account_data = {
            "phone_number": phone_number,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "gender": gender,
            "country": country,
            "timestamp": datetime.utcnow().isoformat()
        }

        run_async(
            sequence_manager.store_step_data(
                phone_number,
                AccountCreationStep.CREATE_ACCOUNT,
                account_data
            )
        )

        # Create user account
        result = run_async(
            auth_service.create_user_with_phone(
                request=None,
                phone_number=phone_number,
                email=email,
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                country=country,
                phone_type="whatsapp",
                phone_verified="yes",
                verification_route="ngpt_wa"
            )
        )

        run_async(
            sequence_manager.update_step(
                phone_number,
                AccountCreationStep.SEND_EMAIL_OTP
            )
        )

        return {
            "message": "Account created successfully",
            "user_id": result["user_id"],
            "next_step": "send_email_otp"
        }

    except Exception as e:
        logger.error(
            "account_creation_failed",
            phone_number=phone_number,
            email=email,
            error=str(e)
        )
        raise self.retry(exc=e)

@celery_app.task(bind=True, base=BaseTaskWithRetry, queue='high')
def send_otp_email_task(self, email: str) -> Dict[str, Any]:
    """Send OTP email with enhanced error handling"""
    logger.info("sending_otp_email", email=email)

    try:
        # Generate and store OTP
        otp = run_async(auth_service.generate_otp())
        run_async(auth_service.store_otp(None, email, otp))

        # Send email
        result = run_async(email_service.send_otp_email(email, otp))

        if not result.get('success'):
            raise SequenceException(
                error_code=SequenceErrorCode.EMAIL_ERROR,
                message="Failed to send OTP email"
            )

        return {"message": "OTP sent successfully"}

    except Exception as e:
        logger.error(
            "otp_email_failed",
            email=email,
            error=str(e)
        )
        raise self.retry(exc=e)

@celery_app.task(bind=True, base=BaseTaskWithRetry)
def verify_email_task(self, email: str, otp: str) -> Dict[str, Any]:
    """Verify email with enhanced validation"""
    logger.info("verifying_email", email=email)

    try:
        # Verify OTP
        verification = run_async(
            auth_service.verify_otp(None, email, otp)
        )

        if verification["valid"]:
            # Mark email as verified
            result = run_async(auth_service.verify_email(None, email))

            # Store verification status
            verification_data = {
                "email": email,
                "verified": True,
                "timestamp": datetime.utcnow().isoformat()
            }

            run_async(
                sequence_manager.store_step_data(
                    email,
                    AccountCreationStep.VERIFY_EMAIL,
                    verification_data
                )
            )

            return {"message": "Email verified successfully"}

        raise SequenceException(
            error_code=SequenceErrorCode.INVALID_OTP,
            message=verification["message"]
        )

    except Exception as e:
        logger.error(
            "email_verification_failed",
            email=email,
            error=str(e)
        )
        raise self.retry(exc=e)

@celery_app.task
def cleanup_expired_sequences() -> None:
    """Cleanup expired sequences periodically"""
    try:
        run_async(sequence_manager.cleanup_expired_sequences())
    except Exception as e:
        logger.error(
            "sequence_cleanup_failed",
            error=str(e)
        )

# Schedule periodic tasks
celery_app.conf.beat_schedule = {
    'cleanup-expired-sequences': {
        'task': 'tasks.celery_tasks.cleanup_expired_sequences',
        'schedule': 3600.0,  # Run every hour
    },
}