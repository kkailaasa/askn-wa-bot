from fastapi import APIRouter, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, List
import logging
from services.ecitizen_auth import (
    get_user_by_phone_or_username, add_phone_to_user, create_user_with_phone,
    verify_email, generate_otp, store_otp, verify_otp,
    KeycloakOperationError, get_user_by_email, get_user_by_phone,
    check_email_exists, store_temp_data, get_temp_data, delete_temp_data,
    rate_limiter
)
from services.email_service import send_otp_email
from services.auth import get_api_key
from utils.twilio_validator import validate_twilio_request
from pydantic import BaseModel, EmailStr, Field
from tasks.celery_tasks import process_question

logger = logging.getLogger(__name__)

router = APIRouter()

class EmailRequest(BaseModel):
    email: EmailStr

class PhoneRequest(BaseModel):
    phone_number: str

class PhoneAuthRequest(BaseModel):
    phone_number: str

class EmailAuthRequest(BaseModel):
    phone_number: str
    email: EmailStr

class CreateUserRequest(BaseModel):
    phone_number: str
    first_name: str
    last_name: str
    gender: str
    country: str

class UserResponse(BaseModel):
    email: str
    enabled: bool
    phoneType: Optional[str]
    phoneNumber: Optional[str]
    gender: Optional[str]
    phoneNumberVerified: Optional[bool]
    firstName: str
    lastName: str

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str

@router.post("/message")
async def reply(request: Request, Body: str = Form(), From: str = Form()):
    # WARNING: Twilio request validation is currently disabled.
    # await validate_twilio_request(request)

    process_question.delay(Body, From)
    return {"status": "Task added"}

@router.post("/get_user_by_email", response_model=UserResponse)
async def get_user_email(email_request: EmailRequest, api_key: str = Depends(get_api_key)):
    try:
        users = get_user_by_email(email_request.email)
        if users and len(users) > 0:
            return UserResponse(**users[0])
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except KeycloakOperationError as e:
        logger.error(f"Keycloak operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/get_user_by_phone", response_model=UserResponse)
async def get_user_phone(phone_request: PhoneRequest, api_key: str = Depends(get_api_key)):
    try:
        user_info = get_user_by_phone(phone_request.phone_number)
        if user_info:
            return UserResponse(**user_info)
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except KeycloakOperationError as e:
        logger.error(f"Keycloak operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/authenticate", response_model=dict)
async def authenticate(auth_request: PhoneAuthRequest, api_key: str = Depends(get_api_key)):
    try:
        user = get_user_by_phone_or_username(auth_request.phone_number)
        if user:
            # Store user data in temporary storage
            store_temp_data(auth_request.phone_number, {"user": user})
            return {"message": "User authenticated", "user": user}
        else:
            store_temp_data(auth_request.phone_number, {"phone_number": auth_request.phone_number})
            return {"message": "User not found", "next_step": "check_email"}
    except KeycloakOperationError as e:
        logger.error(f"Keycloak operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/check_email", response_model=dict)
async def check_email(email_request: EmailAuthRequest, api_key: str = Depends(get_api_key)):
    try:
        temp_data = get_temp_data(email_request.phone_number)
        if not temp_data:
            raise HTTPException(status_code=400, detail="Invalid request sequence")

        users = get_user_by_email(email_request.email)
        if users and len(users) > 0:
            user = users[0]
            result = add_phone_to_user(user['id'], email_request.phone_number)
            delete_temp_data(email_request.phone_number)
            return {"message": "Phone number added to existing account", "user": user}
        else:
            store_temp_data(email_request.phone_number, {**temp_data, "email": email_request.email})
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
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            gender=user_data.gender,
            country=user_data.country
        )
        store_temp_data(result["user_id"], {**temp_data, **user_data.dict(), "user_id": result["user_id"]})
        delete_temp_data(user_data.phone_number)
        return {"message": "User account created", "user_id": result["user_id"], "next_step": "verify_email"}
    except KeycloakOperationError as e:
        logger.error(f"Failed to create user account: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create user account")

@router.post("/send_email_otp", response_model=dict)
async def send_email_otp(email_request: EmailRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(f"send_email_otp:{email_request.email}", limit=3, period=900):  # 3 attempts per 15 minutes
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        otp = generate_otp()
        store_otp(email_request.email, otp)
        if send_otp_email(email_request.email, otp):
            return {"message": "OTP sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send OTP email")
    except Exception as e:
        logger.error(f"Error in send_email_otp: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/verify_email", response_model=dict)
async def verify_email_route(verify_data: VerifyEmailRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(f"verify_email:{verify_data.email}", limit=5, period=300):  # 5 attempts per 5 minutes
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        verification_result = verify_otp(verify_data.email, verify_data.otp)
        if not verification_result["valid"]:
            raise HTTPException(status_code=400, detail=verification_result["message"])

        # If OTP is valid, mark the email as verified in Keycloak
        users = get_user_by_email(verify_data.email)
        if not users or len(users) == 0:
            raise HTTPException(status_code=404, detail="User not found")

        result = verify_email(verify_data.email)
        return {"message": "Email verified successfully."}
    except KeycloakOperationError as e:
        logger.error(f"Failed to verify email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify email")
    except Exception as e:
        logger.error(f"Error in verify_email_route: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")