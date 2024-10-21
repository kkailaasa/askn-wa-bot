from fastapi import APIRouter, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional
from core.config import settings
from services.ecitizen_auth import (
    get_user_by_phone_or_username, add_phone_attributes_to_user, create_user_with_phone,
    verify_email, generate_otp, store_otp, verify_otp,
    KeycloakOperationError, get_user_by_email,
    store_temp_data, get_temp_data, delete_temp_data,
    rate_limiter
)
from services.email_service import send_otp_email
from services.auth import get_api_key
from utils.twilio_validator import validate_twilio_request
from pydantic import BaseModel, EmailStr, Field
from tasks.celery_tasks import process_question
from services import ChatService, MessagingService
from utils.redis_helpers import is_rate_limited
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

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

@router.post("/message")
async def handle_message(
    request: Request,
    Body: str = Form(...),
    From: str = Form(...),
):
    # Validate the request is from Twilio
    #await validate_twilio_request(request)

    # Check rate limiting
    if is_rate_limited(From):
        remaining, reset_time = get_remaining_limit(From)
        logger.warning(f"Rate limit exceeded for {From}. Resets in {reset_time} seconds")
        return JSONResponse(
            content={
                "message": "Rate limit exceeded. Please try again later.",
                "reset_in_seconds": reset_time
            },
            status_code=429
        )

    try:
        # Initialize services
        chat_service = ChatService()
        messaging_service = MessagingService()

        # Get or create conversation ID
        conversation_id = chat_service.get_conversation_id(From)

        # Get response from chat service
        response = chat_service.create_chat_message(
            user=From,
            query=Body,
            conversation_id=conversation_id
        )

        # Send response back to user
        messaging_service.send_message(From, response)

        return JSONResponse(
            content={"message": "Message processed successfully."},
            status_code=200
        )

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        # Try to send error message to user
        try:
            messaging_service = MessagingService()
            messaging_service.send_message(
                From,
                "Sorry, an error occurred while processing your message. Please try again later."
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message: {str(send_error)}")

        return JSONResponse(
            content={"message": "An error occurred while processing your message."},
            status_code=500
        )


@router.post("/check_phone", response_model=dict)
async def check_phone(phone_request: PhoneRequest, api_key: str = Depends(get_api_key)):
    try:
        user = get_user_by_phone_or_username(phone_request.phone_number)
        if user:
            return {"message": "User found", "user": user}
        else:
            store_temp_data(phone_request.phone_number, {"phone_number": phone_request.phone_number})
            return {"message": "User not found", "next_step": "check_email"}
    except KeycloakOperationError as e:
        logger.error(f"Keycloak operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/check_email", response_model=dict)
async def check_email(email_request: EmailRequest, api_key: str = Depends(get_api_key)):
    try:
        temp_data = get_temp_data(email_request.phone_number)
        if not temp_data:
            raise HTTPException(status_code=400, detail="Invalid request sequence")

        user = get_user_by_email(email_request.email)
        if user:
            # Add phone attributes to existing user
            result = add_phone_attributes_to_user(
                user['id'],
                email_request.phone_number,
                phone_type="whatsapp",
                phone_verified="yes",
                verification_route="ngpt_wa"
            )
            delete_temp_data(email_request.phone_number)
            return {"message": "Phone attributes added to existing account", "user": user}
        else:
            store_temp_data(email_request.phone_number, {
                **temp_data,
                "email": email_request.email,
                "phoneType": "whatsapp",
                "phoneVerified": "yes",
                "verificationRoute": "ngpt_wa"
            })
            return {"message": "User not found", "next_step": "create_account"}
    except KeycloakOperationError as e:
        logger.error(f"Keycloak operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/create_account", response_model=dict)
async def create_account(user_data: CreateUserRequest, api_key: str = Depends(get_api_key)):
    temp_data = get_temp_data(user_data.phone_number)
    if not temp_data:
        raise HTTPException(status_code=400, detail="Invalid request sequence")

    try:
        result = create_user_with_phone(
            phone_number=user_data.phone_number,
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            gender=user_data.gender,
            country=user_data.country,
            phone_type=temp_data.get("phoneType", "whatsapp"),
            phone_verified=temp_data.get("phoneVerified", "yes"),
            verification_route=temp_data.get("verificationRoute", "ngpt_wa")
        )
        delete_temp_data(user_data.phone_number)
        return {
            "message": "User account created with UPDATE_PASSWORD action",
            "user_id": result["user_id"],
            "next_step": "verify_email"
        }
    except KeycloakOperationError as e:
        logger.error(f"Failed to create user account: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create user account")

@router.post("/send_email_otp", response_model=dict)
async def send_email_otp(email_request: EmailRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"send_email_otp:{email_request.email}",
        limit=settings.RATE_LIMIT.add_email["limit"],
        period=settings.RATE_LIMIT.add_email["period"]
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
async def verify_email_route(verify_data: VerifyEmailRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"verify_email:{verify_data.email}",
        limit=settings.RATE_LIMIT.verify_email["limit"],
        period=settings.RATE_LIMIT.verify_email["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        verification_result = verify_otp(verify_data.email, verify_data.otp)
        if not verification_result["valid"]:
            raise HTTPException(status_code=400, detail=verification_result["message"])

        # If OTP is valid, mark the email as verified in Keycloak
        result = verify_email(verify_data.email)
        return {"message": "Email verified successfully."}
    except KeycloakOperationError as e:
        logger.error(f"Failed to verify email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify email")
    except Exception as e:
        logger.error(f"Error in verify_email_route: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")