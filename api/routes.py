from fastapi import APIRouter, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional
import logging
from services.ecitizen_auth import (
    get_user_by_phone_or_username,
    get_user_by_email_or_username,
    add_phone_attributes_to_user,
    create_user_with_phone,
    verify_email,
    generate_otp,
    store_otp,
    verify_otp,
    store_temp_data,
    get_temp_data,
    delete_temp_data,
    rate_limiter,
    KeycloakOperationError,
    create_keycloak_admin
)
from keycloak.exceptions import KeycloakError
from services.email_service import send_otp_email
from services.auth import get_api_key
from tasks.celery_tasks import process_message, check_phone, check_email, create_account
from utils.redis_helpers import is_rate_limited, get_remaining_limit
from services import ChatService, MessagingService
from pydantic import BaseModel, EmailStr, Field
from core.config import settings

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

# Response Models
class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str]
    enabled: bool
    first_name: Optional[str]
    last_name: Optional[str]
    phone_number: Optional[str]
    phone_type: Optional[str]
    phone_verified: Optional[str]
    gender: Optional[str]
    country: Optional[str]

@router.post("/message")
async def handle_message(
    request: Request,
    Body: str = Form(...),
    From: str = Form(...)
):
    logger.debug(f"Received message - From: {From}, Body: {Body}")

    # Clean up the phone number format by removing WhatsApp prefix if present
    phone_number = From.replace("whatsapp:", "") if From.startswith("whatsapp:") else From
    
    logger.debug(f"Formatted phone number: {phone_number}")

    # Check rate limiting
    if is_rate_limited(phone_number):
        remaining, reset_time = get_remaining_limit(phone_number)
        logger.warning(f"Rate limit exceeded for {phone_number}. Resets in {reset_time} seconds")
        return JSONResponse(
            content={
                "message": "Rate limit exceeded. Please try again later.",
                "reset_in_seconds": reset_time
            },
            status_code=429
        )

    # Enqueue the message processing task and return immediately
    process_message.delay(phone_number, Body)
    return JSONResponse(
        content={"message": "Message processing started."},
        status_code=202
    )

@router.post("/check_phone", response_model=dict)
async def check_phone_endpoint(phone_request: PhoneRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"create_user:{phone_request.phone_number}",
        limit=settings.rate_limit["create_user"]["limit"],
        period=settings.rate_limit["create_user"]["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        result = check_phone.delay(phone_request.phone_number).get()
        return result
    except KeycloakOperationError as e:
        logger.error(f"Keycloak operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/check_email", response_model=dict)
async def check_email_endpoint(email_request: EmailRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"add_email:{email_request.email}",
        limit=settings.rate_limit["add_email"]["limit"],
        period=settings.rate_limit["add_email"]["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        result = check_email.delay(email_request.phone_number, email_request.email).get()
        return result
    except KeycloakOperationError as e:
        logger.error(f"Failed to check email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check email")

@router.post("/create_account", response_model=dict)
async def create_account_endpoint(user_data: CreateUserRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"create_user:{user_data.phone_number}",
        limit=settings.rate_limit["create_user"]["limit"],
        period=settings.rate_limit["create_user"]["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        result = create_account.delay(
            user_data.phone_number,
            user_data.email,
            user_data.first_name,
            user_data.last_name,
            user_data.gender,
            user_data.country
        ).get()
        return result
    except KeycloakOperationError as e:
        logger.error(f"Failed to create user account: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create user account")

@router.post("/send_email_otp", response_model=dict)
async def send_email_otp(email_request: EmailRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"add_email:{email_request.email}",
        limit=settings.rate_limit["add_email"]["limit"],
        period=settings.rate_limit["add_email"]["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        otp = generate_otp()
        store_otp(email_request.email, otp)
        if send_otp_email(email_request.email, otp):
            return {"message": "OTP sent successfully"}
        else:
            logger.error(f"Failed to send OTP email to {email_request.email}")
            raise HTTPException(status_code=500, detail="Failed to send OTP email")
    except Exception as e:
        logger.error(f"Error in send_email_otp: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/verify_email", response_model=dict)
async def verify_email_endpoint(verify_data: VerifyEmailRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"verify_email:{verify_data.email}",
        limit=settings.rate_limit["verify_email"]["limit"],
        period=settings.rate_limit["verify_email"]["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        verification_result = verify_otp(verify_data.email, verify_data.otp)
        if not verification_result["valid"]:
            raise HTTPException(status_code=400, detail=verification_result["message"])

        result = verify_email(verify_data.email)
        return {"message": "Email verified successfully."}
    except KeycloakOperationError as e:
        logger.error(f"Failed to verify email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify email")
    except Exception as e:
        logger.error(f"Error in verify_email_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")