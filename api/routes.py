from fastapi import APIRouter, Form, HTTPException, Depends, Request, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, Union, Tuple, AsyncGenerator
import asyncio
from datetime import datetime, timedelta
import logging
from uuid import uuid4
from pydantic import BaseModel, EmailStr
from contextlib import asynccontextmanager
import structlog
import functools
from sqlalchemy.ext.asyncio import AsyncSession 

# Core imports
from core.config import settings
from core.sequence_errors import (
    SequenceStatus,
    SequenceErrorCode,
    SequenceException,
    SequenceResponse,
    handle_sequence_error
)

# Database imports
from db_scripts.base import get_db, get_db_dependency

# Service imports
from services import (
    ChatService,
    MessagingService,
    ECitizenAuthService,
    sequence_manager,
    AccountCreationStep
)

# Utility imports
from utils import (
    safe_operation_execution,
    check_system_health,
    with_request_tracking,
    RequestContext,
    track_request,
    log_error,
    log_conversation,
    validate_phone_format,
    validate_email_format,
    validate_name_format,
    validate_gender,
    validate_country,
    rate_limiter
)
# Task imports
from tasks.celery_tasks import (
    process_message,
    check_phone,
    check_email,
    create_account,
    send_otp_email_task,
    verify_email_task
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Request Models
class PhoneRequest(BaseModel):
    phone_number: str

class EmailRequest(BaseModel):
    phone_number: str
    email: EmailStr

class CreateUserRequest(BaseModel):
    phone_number: str
    email: EmailStr
    first_name: str
    last_name: str
    gender: str
    country: str

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str

class UserInfoRequest(BaseModel):
    identifier: str
    identifier_type: str = "email"  # can be "email" or "phone"

# Response Models
class UserAttributesModel(BaseModel):
    phoneType: Optional[str]
    phoneNumber: Optional[str]
    gender: Optional[str]
    phoneVerified: Optional[str]
    country: Optional[str]
    verificationRoute: Optional[str]

class UserInfoResponse(BaseModel):
    username: Optional[str]
    email: Optional[str]
    enabled: Optional[bool]
    firstName: Optional[str]
    lastName: Optional[str]
    attributes: Optional[UserAttributesModel]
    message: str

class RequestContext:
    """Request context holder"""
    _context = {}

    @classmethod
    def get_request_id(cls) -> Optional[str]:
        return cls._context.get("request_id")

    @classmethod
    def set_request_id(cls, request_id: str) -> None:
        cls._context["request_id"] = request_id

    @classmethod
    def clear(cls) -> None:
        cls._context.clear()

@asynccontextmanager
async def track_request(request: Request) -> AsyncGenerator[str, None]:
    """Context manager for request tracking"""
    request_id = str(uuid4())
    existing_request_id = request.headers.get("X-Request-ID")
    if existing_request_id:
        request_id = existing_request_id

    RequestContext.set_request_id(request_id)
    logger = structlog.get_logger().bind(request_id=request_id)

    try:
        logger.info(
            "request_started",
            path=request.url.path,
            method=request.method,
            client_ip=request.client.host
        )
        yield request_id
    finally:
        logger.info("request_completed")
        RequestContext.clear()

async def get_rate_limit_info(request: Request, identifier: str) -> Tuple[bool, int]:
    """Get rate limit status and reset time"""
    try:
        is_limited = await is_rate_limited(request, identifier)
        _, reset_time = await get_remaining_limit(request, identifier)
        return is_limited, reset_time
    except Exception as e:
        logger.error(f"Rate limit check error: {str(e)}")
        return False, 0

async def safe_operation_execution(
    operation: str,
    func: callable,
    timeout: int,
    **kwargs
) -> Dict[str, Any]:
    """Generic safe execution function for operations and tasks"""
    try:
        async with asyncio.timeout(timeout):
            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                task = func.delay(**kwargs)
                result = await asyncio.wait_for(task.get(), timeout=timeout-2)
            return result
    except asyncio.TimeoutError:
        logger.error(f"Timeout in {operation}")
        raise SequenceException(
            error_code=SequenceErrorCode.TIMEOUT,
            message=f"{operation} operation timed out",
            status_code=503,
            retry_after=30
        )
    except Exception as e:
        logger.error(f"Error in {operation}: {str(e)}")
        raise SequenceException(
            error_code=SequenceErrorCode.SYSTEM_ERROR,
            message=f"{operation} operation failed",
            status_code=500
        )

def with_request_tracking(operation_name: str):
    """Decorator for request tracking and error handling"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            async with track_request(request) as request_id:
                try:
                    background_tasks = kwargs.get('background_tasks')
                    result = await func(request, *args, **kwargs)

                    # Add request ID to response headers if it's a Response object
                    if hasattr(result, 'headers'):
                        result.headers["X-Request-ID"] = request_id

                    return result
                except Exception as e:
                    error = handle_sequence_error(e, operation_name)
                    if background_tasks:
                        background_tasks.add_task(
                            log_error,
                            error_type=type(error).__name__,
                            error_message=str(error),
                            metadata={
                                "request_id": request_id,
                                "operation": operation_name
                            }
                        )
                    raise error
        return wrapper
    return decorator

async def verify_api_key(x_api_key: str = Header(None)):
    """Global API key verification"""
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=403,
            detail=SequenceResponse.failure(
                message="Invalid API key",
                error_code=SequenceErrorCode.INVALID_DATA
            ).to_dict()
        )
    return x_api_key

@router.post("/message")
@with_request_tracking("message_handling")
async def handle_message(
    request: Request,
    background_tasks: BackgroundTasks,
    Body: str = Form(...),
    From: str = Form(...),
    api_key: str = Depends(verify_api_key)
):
    """Handle incoming WhatsApp messages"""
    phone_number = From.replace("whatsapp:", "") if From.startswith("whatsapp:") else From

    # Rate limiting check
    is_limited, reset_time = await get_rate_limit_info(request, phone_number)
    if is_limited:
        return JSONResponse(
            content=SequenceResponse.blocked(
                message="Rate limit exceeded. Please try again later.",
                retry_after=reset_time
            ).to_dict(),
            status_code=429
        )

    chat_service = ChatService()

    # Get conversation context and process message
    try:
        conversation_id = await safe_operation_execution(
            "get_conversation",
            chat_service.get_conversation_id,
            settings.CHAT_TIMEOUT,
            phone_number=phone_number
        )

        response = await safe_operation_execution(
            "create_message",
            chat_service.create_chat_message,
            settings.CHAT_TIMEOUT,
            phone_number=phone_number,
            message=Body,
            conversation_id=conversation_id
        )

        # Handle auth verification if needed
        if response.get("needs_auth_verification"):
            auth_result = await safe_operation_execution(
                "auth_verification",
                handle_sequence_operation,
                settings.AUTH_TIMEOUT,
                operation=response["required_operation"],
                data=response.get("operation_data", {})
            )

            response = await safe_operation_execution(
                "create_message_with_auth",
                chat_service.create_chat_message,
                settings.CHAT_TIMEOUT,
                phone_number=phone_number,
                message=Body,
                conversation_id=conversation_id,
                auth_context=auth_result
            )

        # Log successful conversation
        background_tasks.add_task(
            log_conversation,
            phone_number=phone_number,
            message=Body,
            response=response.get("message"),
            conversation_id=conversation_id,
            metadata={"status": "success"}
        )

        return SequenceResponse.success(
            message=response.get("message")
        ).to_dict()

    except Exception as e:
        raise handle_sequence_error(e, "message_handling")

@router.post("/check_phone", response_model=Dict[str, Any])
@with_request_tracking("check_phone")
async def check_phone_endpoint(
    request: Request,
    phone_request: PhoneRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Check phone number and start registration sequence"""
    try:
        # Input validation
        if not validate_phone_format(phone_request.phone_number):
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_PHONE,
                message="Invalid phone number format"
            )

        # Rate limit check
        is_limited, reset_time = await get_rate_limit_info(
            request,
            f"check_phone:{phone_request.phone_number}"
        )
        if is_limited:
            return JSONResponse(
                content=SequenceResponse.blocked(
                    message="Too many attempts. Please try again later.",
                    retry_after=reset_time
                ).to_dict(),
                status_code=429
            )

        # Sequence validation and phone check
        await safe_operation_execution(
            "sequence_validation",
            sequence_manager.validate_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=phone_request.phone_number,
            current_step=AccountCreationStep.CHECK_PHONE
        )

        # Process phone check
        result = await safe_operation_execution(
            "phone_check",
            check_phone.delay,
            settings.AUTH_TIMEOUT,
            phone_number=phone_request.phone_number
        )

        # Store step data
        await safe_operation_execution(
            "store_step_data",
            sequence_manager.store_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=phone_request.phone_number,
            step=AccountCreationStep.CHECK_PHONE,
            data={
                "phone_number": phone_request.phone_number,
                "verification_status": result.get("user_found", False),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        # Update sequence to next step
        await safe_operation_execution(
            "update_sequence",
            sequence_manager.update_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=phone_request.phone_number,
            step=AccountCreationStep.CHECK_EMAIL
        )

        return SequenceResponse.success(
            message="Phone check completed",
            data=result,
            next_action="check_email"
        ).to_dict()

    except Exception as e:
        raise

@router.post("/check_email", response_model=Dict[str, Any])
@with_request_tracking("check_email")
async def check_email_endpoint(
    request: Request,
    email_request: EmailRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Check email and continue registration sequence"""
    try:
        # Input validation
        if not validate_email_format(email_request.email):
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_EMAIL,
                message="Invalid email format"
            )

        # Rate limit check
        is_limited, reset_time = await get_rate_limit_info(
            request,
            f"check_email:{email_request.email}"
        )
        if is_limited:
            return JSONResponse(
                content=SequenceResponse.blocked(
                    message="Too many attempts. Please try again later.",
                    retry_after=reset_time
                ).to_dict(),
                status_code=429
            )

        # Sequence validation and email check
        await safe_operation_execution(
            "sequence_validation",
            sequence_manager.validate_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=email_request.phone_number,
            current_step=AccountCreationStep.CHECK_EMAIL
        )

        # Check previous step data
        prev_data = await safe_operation_execution(
            "get_step_data",
            sequence_manager.get_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=email_request.phone_number
        )

        if not prev_data or prev_data.get("phone_number") != email_request.phone_number:
            raise SequenceException(
                error_code=SequenceErrorCode.SEQUENCE_VIOLATION,
                message="Invalid sequence state or mismatched phone number"
            )

        # Process email check
        result = await safe_operation_execution(
            "email_check",
            check_email.delay,
            settings.AUTH_TIMEOUT,
            phone_number=email_request.phone_number,
            email=email_request.email
        )

        # Store step data
        await safe_operation_execution(
            "store_step_data",
            sequence_manager.store_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=email_request.phone_number,
            step=AccountCreationStep.CHECK_EMAIL,
            data={
                "email": email_request.email,
                "verification_status": result.get("email_exists", False),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        # Update sequence to next step
        await safe_operation_execution(
            "update_sequence",
            sequence_manager.update_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=email_request.phone_number,
            step=AccountCreationStep.CREATE_ACCOUNT
        )

        return SequenceResponse.success(
            message="Email check completed",
            data=result,
            next_action="create_account"
        ).to_dict()

    except Exception as e:
        raise

@router.post("/create_account", response_model=Dict[str, Any])
@with_request_tracking("create_account")
async def create_account_endpoint(
    request: Request,
    user_data: CreateUserRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Create user account"""
    try:
        # Comprehensive input validation
        validation_errors = []
        if not validate_phone_format(user_data.phone_number):
            validation_errors.append("Invalid phone number format")
        if not validate_email_format(user_data.email):
            validation_errors.append("Invalid email format")
        if not validate_name_format(user_data.first_name):
            validation_errors.append("Invalid first name format")
        if not validate_name_format(user_data.last_name):
            validation_errors.append("Invalid last name format")
        if not validate_gender(user_data.gender):
            validation_errors.append("Invalid gender value")
        if not validate_country(user_data.country):
            validation_errors.append("Invalid country code")

        if validation_errors:
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_DATA,
                message="Invalid user data format",
                details={"validation_errors": validation_errors}
            )

        # Rate limit check
        is_limited, reset_time = await get_rate_limit_info(
            request,
            f"create_account:{user_data.phone_number}"
        )
        if is_limited:
            return JSONResponse(
                content=SequenceResponse.blocked(
                    message="Too many account creation attempts. Please try again later.",
                    retry_after=reset_time
                ).to_dict(),
                status_code=429
            )

        # Sequence validation
        await safe_operation_execution(
            "sequence_validation",
            sequence_manager.validate_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=user_data.phone_number,
            current_step=AccountCreationStep.CREATE_ACCOUNT
        )

        # Verify previous step data consistency
        prev_data = await safe_operation_execution(
            "get_step_data",
            sequence_manager.get_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=user_data.phone_number
        )

        # Validate data consistency with previous steps
        if not prev_data:
            raise SequenceException(
                error_code=SequenceErrorCode.SEQUENCE_VIOLATION,
                message="Previous step data not found"
            )

        if prev_data.get("email") != user_data.email or prev_data.get("phone_number") != user_data.phone_number:
            raise SequenceException(
                error_code=SequenceErrorCode.DATA_MISMATCH,
                message="User data doesn't match previous step data",
                details={
                    "prev_email": prev_data.get("email"),
                    "new_email": user_data.email,
                    "prev_phone": prev_data.get("phone_number"),
                    "new_phone": user_data.phone_number
                }
            )

        # Create account with retries if needed
        try:
            result = await safe_operation_execution(
                "account_creation",
                create_account.delay,
                settings.ACCOUNT_CREATION_TIMEOUT,
                **user_data.dict()
            )

            if not result.get("user_id"):
                raise SequenceException(
                    error_code=SequenceErrorCode.KEYCLOAK_ERROR,
                    message="Failed to create user account",
                    details=result.get("error")
                )

        except Exception as e:
            logger.error(f"Account creation failed: {str(e)}")
            # Store failure context for potential recovery
            background_tasks.add_task(
                store_error_context,
                user_data.phone_number,
                {
                    "operation": "create_account",
                    "error": str(e),
                    "user_data": user_data.dict()
                }
            )
            raise

        # Store successful account creation data
        await safe_operation_execution(
            "store_step_data",
            sequence_manager.store_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=user_data.phone_number,
            step=AccountCreationStep.CREATE_ACCOUNT,
            data={
                **user_data.dict(),
                "user_id": result.get("user_id"),
                "creation_timestamp": datetime.utcnow().isoformat(),
                "verification_status": "pending"
            }
        )

        # Update sequence to next step
        await safe_operation_execution(
            "update_sequence",
            sequence_manager.update_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=user_data.phone_number,
            step=AccountCreationStep.SEND_EMAIL_OTP
        )

        # Log successful account creation
        background_tasks.add_task(
            log_conversation,
            phone_number=user_data.phone_number,
            message="Account created successfully",
            response="Success",
            metadata={
                "user_id": result.get("user_id"),
                "email": user_data.email,
                "registration_timestamp": datetime.utcnow().isoformat()
            }
        )

        return SequenceResponse.success(
            message="Account created successfully",
            data={
                "user_id": result.get("user_id"),
                "verification_pending": True
            },
            next_action="send_email_otp"
        ).to_dict()

    except SequenceException:
        # Let the decorator handle SequenceExceptions
        raise
    except Exception as e:
        # Convert unexpected errors to SequenceException
        raise SequenceException(
            error_code=SequenceErrorCode.SYSTEM_ERROR,
            message="An unexpected error occurred during account creation",
            details={"error": str(e)}
        )

@router.post("/send_email_otp", response_model=Dict[str, Any])
@with_request_tracking("send_email_otp")
async def send_email_otp_endpoint(
    request: Request,
    email_request: EmailRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Send email OTP for verification"""
    try:
        # Input validation
        if not validate_email_format(email_request.email):
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_EMAIL,
                message="Invalid email format"
            )

        if not validate_phone_format(email_request.phone_number):
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_PHONE,
                message="Invalid phone number format"
            )

        # Rate limit check
        is_limited, reset_time = await get_rate_limit_info(
            request,
            f"send_otp:{email_request.email}"
        )
        if is_limited:
            return JSONResponse(
                content=SequenceResponse.blocked(
                    message="Too many OTP requests. Please try again later.",
                    retry_after=reset_time
                ).to_dict(),
                status_code=429
            )

        # Sequence validation
        await safe_operation_execution(
            "sequence_validation",
            sequence_manager.validate_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=email_request.phone_number,
            current_step=AccountCreationStep.SEND_EMAIL_OTP
        )

        # Verify previous step data
        prev_data = await safe_operation_execution(
            "get_step_data",
            sequence_manager.get_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=email_request.phone_number
        )

        if not prev_data:
            raise SequenceException(
                error_code=SequenceErrorCode.SEQUENCE_VIOLATION,
                message="Previous step data not found"
            )

        # Validate data consistency
        if prev_data.get("email") != email_request.email:
            raise SequenceException(
                error_code=SequenceErrorCode.DATA_MISMATCH,
                message="Email doesn't match previous step data"
            )

        # Send OTP email
        result = await safe_operation_execution(
            "send_otp",
            send_otp_email_task.delay,
            settings.EMAIL_TIMEOUT,
            email=email_request.email
        )

        if not result.get("success", False):
            raise SequenceException(
                error_code=SequenceErrorCode.EMAIL_ERROR,
                message="Failed to send OTP email",
                details=result.get("error")
            )

        # Store OTP attempt data
        await safe_operation_execution(
            "store_step_data",
            sequence_manager.store_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=email_request.phone_number,
            step=AccountCreationStep.SEND_EMAIL_OTP,
            data={
                "email": email_request.email,
                "otp_sent": True,
                "otp_sent_at": datetime.utcnow().isoformat(),
                "attempts": prev_data.get("attempts", 0) + 1
            }
        )

        # Update sequence to next step
        await safe_operation_execution(
            "update_sequence",
            sequence_manager.update_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=email_request.phone_number,
            step=AccountCreationStep.VERIFY_EMAIL
        )

        # Log OTP sending
        background_tasks.add_task(
            log_conversation,
            phone_number=email_request.phone_number,
            message="OTP email sent",
            response="Success",
            metadata={
                "email": email_request.email,
                "otp_sent_at": datetime.utcnow().isoformat()
            }
        )

        return SequenceResponse.success(
            message="OTP sent successfully",
            data={"email": email_request.email},
            next_action="verify_email"
        ).to_dict()

    except Exception as e:
        # Let decorator handle the error
        raise

@router.post("/verify_email", response_model=Dict[str, Any])
@with_request_tracking("verify_email")
async def verify_email_endpoint(
    request: Request,
    verify_data: VerifyEmailRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Verify email using OTP"""
    try:
        # Input validation
        if not validate_email_format(verify_data.email):
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_EMAIL,
                message="Invalid email format"
            )

        # Rate limit check for verification attempts
        is_limited, reset_time = await get_rate_limit_info(
            request,
            f"verify_email:{verify_data.email}"
        )
        if is_limited:
            return JSONResponse(
                content=SequenceResponse.blocked(
                    message="Too many verification attempts. Please try again later.",
                    retry_after=reset_time
                ).to_dict(),
                status_code=429
            )

        # Get the associated phone number from previous step
        prev_data = await safe_operation_execution(
            "get_step_data",
            sequence_manager.get_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=verify_data.email
        )

        if not prev_data or not prev_data.get("phone_number"):
            raise SequenceException(
                error_code=SequenceErrorCode.SEQUENCE_VIOLATION,
                message="No active verification session found"
            )

        phone_number = prev_data.get("phone_number")

        # Sequence validation
        await safe_operation_execution(
            "sequence_validation",
            sequence_manager.validate_step,
            settings.SEQUENCE_TIMEOUT,
            identifier=phone_number,
            current_step=AccountCreationStep.VERIFY_EMAIL
        )

        # Check OTP expiry and attempt limits
        otp_data = prev_data.get("otp_sent_at")
        if otp_data:
            otp_sent_time = datetime.fromisoformat(otp_data)
            if datetime.utcnow() - otp_sent_time > timedelta(minutes=10):
                raise SequenceException(
                    error_code=SequenceErrorCode.EXPIRED,
                    message="OTP has expired. Please request a new one.",
                    status_code=400
                )

        # Verify OTP
        verification_result = await safe_operation_execution(
            "verify_otp",
            verify_email_task.delay,
            settings.AUTH_TIMEOUT,
            email=verify_data.email,
            otp=verify_data.otp
        )

        if not verification_result.get("valid", False):
            # Increment failed attempts counter
            current_attempts = prev_data.get("verification_attempts", 0) + 1
            await safe_operation_execution(
                "store_step_data",
                sequence_manager.store_step_data,
                settings.SEQUENCE_TIMEOUT,
                identifier=phone_number,
                step=AccountCreationStep.VERIFY_EMAIL,
                data={
                    "verification_attempts": current_attempts,
                    "last_attempt": datetime.utcnow().isoformat()
                }
            )

            if current_attempts >= settings.MAX_OTP_ATTEMPTS:
                raise SequenceException(
                    error_code=SequenceErrorCode.MAX_ATTEMPTS_EXCEEDED,
                    message="Maximum verification attempts exceeded. Please request a new OTP.",
                    status_code=400
                )

            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_OTP,
                message="Invalid OTP",
                details={"attempts_remaining": settings.MAX_OTP_ATTEMPTS - current_attempts}
            )

        # Mark email as verified in Keycloak
        await safe_operation_execution(
            "update_email_verification",
            verify_email_task.delay,
            settings.AUTH_TIMEOUT,
            email=verify_data.email
        )

        # Store verification success
        await safe_operation_execution(
            "store_step_data",
            sequence_manager.store_step_data,
            settings.SEQUENCE_TIMEOUT,
            identifier=phone_number,
            step=AccountCreationStep.VERIFY_EMAIL,
            data={
                "email": verify_data.email,
                "verified": True,
                "verified_at": datetime.utcnow().isoformat()
            }
        )

        # Log verification success
        background_tasks.add_task(
            log_conversation,
            phone_number=phone_number,
            message="Email verified successfully",
            response="Success",
            metadata={
                "email": verify_data.email,
                "verified_at": datetime.utcnow().isoformat()
            }
        )

        return SequenceResponse.success(
            message="Email verified successfully",
            data={
                "email": verify_data.email,
                "verified": True
            }
        ).to_dict()

    except Exception as e:
        # Let decorator handle the error
        raise

@router.post("/get_user_info", response_model=UserInfoResponse)
@with_request_tracking("get_user_info")
async def get_user_info_endpoint(
    request: Request,
    user_request: UserInfoRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_dependency),
    api_key: str = Depends(verify_api_key)
):
    """Get comprehensive user information based on email or phone number"""
    try:
        # Input validation with specific error messages
        if user_request.identifier_type not in ["email", "phone"]:
            raise SequenceException(
                error_code=SequenceErrorCode.INVALID_DATA,
                message="Invalid identifier type",
                details={"allowed_types": ["email", "phone"]}
            )

        if user_request.identifier_type == "email":
            if not validate_email_format(user_request.identifier):
                raise SequenceException(
                    error_code=SequenceErrorCode.INVALID_EMAIL,
                    message="Invalid email format"
                )
        else:  # phone
            if not validate_phone_format(user_request.identifier):
                raise SequenceException(
                    error_code=SequenceErrorCode.INVALID_PHONE,
                    message="Invalid phone number format"
                )

        # Rate limit check with identifier-specific limits
        is_limited, reset_time = await rate_limiter.is_rate_limited(
            request=request,
            rate_limit_type="get_user_info",
            settings=settings
        )
        if is_limited:
            return JSONResponse(
                content=SequenceResponse.blocked(
                    message="Too many lookup attempts. Please try again later.",
                    retry_after=reset_time
                ).to_dict(),
                status_code=429
            )

        # Initialize auth service
        auth_service = EcitzenAuthService()

        # Get user data based on identifier type
        try:
            async with asyncio.timeout(settings.AUTH_TIMEOUT):
                user = await safe_operation_execution(
                    "get_user_info",
                    auth_service.get_user_by_email_or_username if user_request.identifier_type == "email"
                    else auth_service.get_user_by_phone_or_username,
                    settings.AUTH_TIMEOUT,
                    identifier=user_request.identifier
                )

                if not user:
                    # Log the not found case using async logging
                    async with get_db() as log_db:
                        await log_conversation(
                            db=log_db,
                            phone_number=user_request.identifier if user_request.identifier_type == "phone" else None,
                            message=f"User lookup failed for {user_request.identifier}",
                            response="Not Found",
                            metadata={
                                "identifier_type": user_request.identifier_type,
                                "lookup_timestamp": datetime.utcnow().isoformat()
                            }
                        )

                    return UserInfoResponse(
                        message="User not found",
                        username=None,
                        email=None,
                        enabled=None,
                        firstName=None,
                        lastName=None,
                        attributes=None
                    )

                # Process user attributes safely
                attributes = user.get("attributes", {})
                user_attributes = UserAttributesModel(
                    phoneType=next(iter(attributes.get("phoneType", [])), None),
                    phoneNumber=next(iter(attributes.get("phoneNumber", [])), None),
                    gender=next(iter(attributes.get("gender", [])), None),
                    phoneVerified=next(iter(attributes.get("phoneVerified", [])), None),
                    country=next(iter(attributes.get("country", [])), None),
                    verificationRoute=next(iter(attributes.get("verificationRoute", [])), None)
                )

                # Cache the result if successful
                await safe_operation_execution(
                    "cache_user_info",
                    sequence_manager.store_step_data,
                    settings.CACHE_TIMEOUT,
                    identifier=f"user_info:{user_request.identifier}",
                    step="user_info",
                    data={
                        "user_data": user,
                        "cached_at": datetime.utcnow().isoformat(),
                        "identifier_type": user_request.identifier_type
                    }
                )

                # Log successful retrieval using async logging
                async with get_db() as log_db:
                    await log_conversation(
                        db=log_db,
                        phone_number=user_attributes.phoneNumber,
                        message=f"User info retrieved for {user_request.identifier}",
                        response="Success",
                        metadata={
                            "identifier_type": user_request.identifier_type,
                            "lookup_timestamp": datetime.utcnow().isoformat(),
                            "user_id": user.get("id")
                        }
                    )

                # Prepare and return response
                response = UserInfoResponse(
                    username=user.get("username"),
                    email=user.get("email"),
                    enabled=user.get("enabled"),
                    firstName=user.get("firstName"),
                    lastName=user.get("lastName"),
                    attributes=user_attributes,
                    message="User information retrieved successfully"
                )

                # Add additional security headers if needed
                headers = {
                    "X-User-Found": "true",
                    "X-Result-Timestamp": datetime.utcnow().isoformat()
                }

                return JSONResponse(
                    content=response.dict(),
                    headers=headers,
                    status_code=200
                )

        except asyncio.TimeoutError:
            raise SequenceException(
                error_code=SequenceErrorCode.TIMEOUT,
                message="Operation timed out while retrieving user information",
                status_code=503,
                retry_after=30
            )

        except Exception as e:
            # Log specific error details
            logger.error(
                "User info retrieval failed",
                extra={
                    "identifier": user_request.identifier,
                    "identifier_type": user_request.identifier_type,
                    "error": str(e)
                }
            )

            # Store error context using async logging
            async with get_db() as error_db:
                await log_error(
                    db=error_db,
                    error_type="KeycloakError",
                    error_message=str(e),
                    metadata={
                        "operation": "get_user_info",
                        "identifier": user_request.identifier,
                        "identifier_type": user_request.identifier_type,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )

            raise SequenceException(
                error_code=SequenceErrorCode.KEYCLOAK_ERROR,
                message="Failed to retrieve user information",
                status_code=500
            )

    except SequenceException as e:
        # Add error context to response headers
        e.headers = {
            "X-Error-Code": e.error_code,
            "X-Error-Time": datetime.utcnow().isoformat()
        }
        # Log sequence exception
        async with get_db() as error_db:
            await log_error(
                db=error_db,
                error_type="SequenceException",
                error_message=str(e),
                metadata={
                    "error_code": e.error_code,
                    "identifier": user_request.identifier,
                    "identifier_type": user_request.identifier_type
                }
            )
        raise

    except Exception as e:
        # Log unexpected exception
        async with get_db() as error_db:
            await log_error(
                db=error_db,
                error_type="UnexpectedError",
                error_message=str(e),
                metadata={
                    "identifier": user_request.identifier,
                    "identifier_type": user_request.identifier_type
                }
            )
        raise SequenceException(
            error_code=SequenceErrorCode.SYSTEM_ERROR,
            message="An unexpected error occurred while retrieving user information",
            status_code=500,
            details={"error": str(e)}
        )

@router.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION
    }

async def store_error_context(phone_number: str, error_context: Dict[str, Any]):
    """Background task to store error context"""
    try:
        async with asyncio.timeout(5):
            sequence_manager.store_step_data(phone_number, {
                "last_error": {
                    **error_context,
                    "timestamp": datetime.utcnow().isoformat()
                }
            })
    except Exception as e:
        logger.error(f"Failed to store error context: {str(e)}")

async def safe_sequence_check(phone_number: str) -> Optional[Dict[str, Any]]:
    """Safely check sequence state with timeout"""
    try:
        async with asyncio.timeout(3):
            return sequence_manager.get_step_data(phone_number)
    except asyncio.TimeoutError:
        logger.error(f"Timeout getting sequence state for {phone_number}")
        return None
    except Exception as e:
        logger.error(f"Error getting sequence state: {str(e)}")
        return None

async def safe_task_execution(task_func, timeout: int = 15, **kwargs) -> Dict[str, Any]:
    """Safely execute a Celery task with timeout"""
    try:
        async with asyncio.timeout(timeout):
            task = task_func.delay(**kwargs)
            return await asyncio.wait_for(task.get(), timeout=timeout-2)
    except asyncio.TimeoutError:
        raise SequenceException(
            error_code=SequenceErrorCode.KEYCLOAK_ERROR,
            message="Operation timed out",
            status_code=503,
            retry_after=30
        )
    except Exception as e:
        logger.error(f"Task execution error: {str(e)}")
        raise SequenceException(
            error_code=SequenceErrorCode.KEYCLOAK_ERROR,
            message="Operation failed",
            status_code=500
        )

# Rate limiting helper function
async def check_rate_limit(request: Request, rate_limit_type: str) -> None:
    """Check rate limit and raise exception if exceeded"""
    is_limited, retry_after = await rate_limiter.is_rate_limited(
        request=request,
        rate_limit_type=rate_limit_type,
        settings=settings
    )

    if is_limited:
        raise SequenceException(
            error_code=SequenceErrorCode.RATE_LIMIT,
            message="Rate limit exceeded",
            status_code=429,
            retry_after=retry_after
        )

# Get remaining limit helper function
async def get_rate_limit_info(request: Request, rate_limit_type: str) -> Tuple[int, int]:
    """Get remaining rate limit and reset time"""
    remaining, reset_time = await rate_limiter.get_remaining_limit(
        request=request,
        rate_limit_type=rate_limit_type,
        settings=settings
    )
    return remaining, reset_time

@router.get("/health")
async def health_check():
    """Enhanced health check endpoint"""
    try:
        # Check core dependencies
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": settings.APP_VERSION,
            "components": {}
        }

        # Check Redis
        try:
            async with asyncio.timeout(2):
                redis_start = time.time()
                await sequence_manager.ping()
                redis_latency = time.time() - redis_start
                health_status["components"]["redis"] = {
                    "status": "healthy",
                    "latency_ms": round(redis_latency * 1000, 2)
                }
        except Exception as e:
            health_status["components"]["redis"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        # Check Keycloak
        try:
            async with asyncio.timeout(2):
                auth_service = EcitzenAuthService()
                auth_start = time.time()
                await auth_service.health_check()
                auth_latency = time.time() - auth_start
                health_status["components"]["keycloak"] = {
                    "status": "healthy",
                    "latency_ms": round(auth_latency * 1000, 2)
                }
        except Exception as e:
            health_status["components"]["keycloak"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        return health_status

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }