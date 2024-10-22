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
from utils.twilio_validator import validate_twilio_request
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

@router.post("/check_phone", response_model=dict)
async def check_phone(phone_request: PhoneRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"create_user:{phone_request.phone_number}",
        limit=settings.rate_limit["create_user"]["limit"],
        period=settings.rate_limit["create_user"]["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        user = get_user_by_phone_or_username(phone_request.phone_number)
        if user:
            # Add debug logging
            logger.debug(f"Raw user object from Keycloak: {user}")
            
            # Format user response with enhanced information
            user_response = {
                "id": user.get('id'),
                "username": user.get('username'),
                "email": user.get('email'),
                "enabled": user.get('enabled', False),
                # Access first and last names directly from the user object
                "first_name": user.get('firstName', user.get('first_name')) or '',
                "last_name": user.get('lastName', user.get('last_name')) or '',
                "phone_number": user.get('attributes', {}).get('phoneNumber', [None])[0],
                "phone_type": user.get('attributes', {}).get('phoneType', [None])[0],
                "phone_verified": user.get('attributes', {}).get('phoneVerified', [None])[0],
                "gender": user.get('attributes', {}).get('gender', [None])[0],
                "country": user.get('attributes', {}).get('country', [None])[0]
            }

            # Log the formatted response
            logger.debug(f"Formatted user response: {user_response}")

            # If user exists but has no email, store temp data and proceed to check_email
            if not user.get('email'):
                store_temp_data(phone_request.phone_number, {
                    "phone_number": phone_request.phone_number,
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
            store_temp_data(phone_request.phone_number, {"phone_number": phone_request.phone_number})
            return {"message": "User not found", "next_step": "check_email"}
    except KeycloakOperationError as e:
        logger.error(f"Keycloak operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Update the format_user_response function in check_email route as well
def format_user_response(user):
    logger.debug(f"Raw user object in format_user_response: {user}")
    formatted = {
        "id": user.get('id'),
        "username": user.get('username'),
        "email": user.get('email'),
        "enabled": user.get('enabled', False),
        "first_name": user.get('firstName', user.get('first_name')) or '',
        "last_name": user.get('lastName', user.get('last_name')) or '',
        "phone_number": user.get('attributes', {}).get('phoneNumber', [None])[0],
        "phone_type": user.get('attributes', {}).get('phoneType', [None])[0],
        "phone_verified": user.get('attributes', {}).get('phoneVerified', [None])[0],
        "gender": user.get('attributes', {}).get('gender', [None])[0],
        "country": user.get('attributes', {}).get('country', [None])[0]
    }
    logger.debug(f"Formatted user response: {formatted}")
    return formatted

@router.post("/check_email", response_model=dict)
async def check_email(email_request: EmailRequest, api_key: str = Depends(get_api_key)):
    if rate_limiter.is_rate_limited(
        f"add_email:{email_request.email}",
        limit=settings.rate_limit["add_email"]["limit"],
        period=settings.rate_limit["add_email"]["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        temp_data = get_temp_data(email_request.phone_number)
        if not temp_data:
            raise HTTPException(status_code=400, detail="Invalid request sequence")

        # Get both users
        phone_user = get_user_by_phone_or_username(email_request.phone_number)
        email_user = get_user_by_email_or_username(email_request.email)

        # Format user response function
        def format_user_response(user):
            return {
                "id": user.get('id'),
                "username": user.get('username'),
                "email": user.get('email'),
                "enabled": user.get('enabled', False),
                # Updated to use correct case for name fields
                "first_name": user.get('firstName') or '',  # Changed from firstName to correct case
                "last_name": user.get('lastName') or '',    # Changed from lastName to correct case
                "phone_number": user.get('attributes', {}).get('phoneNumber', [None])[0],
                "phone_type": user.get('attributes', {}).get('phoneType', [None])[0],
                "phone_verified": user.get('attributes', {}).get('phoneVerified', [None])[0],
                "gender": user.get('attributes', {}).get('gender', [None])[0],
                "country": user.get('attributes', {}).get('country', [None])[0]
            }

        if phone_user and email_user:
            # Both users exist - we need to merge them
            try:
                keycloak_admin = create_keycloak_admin()

                # First, update the phone user with the email user's data
                email_attributes = email_user.get('attributes', {})
                phone_attributes = phone_user.get('attributes', {})

                # Merge attributes
                merged_attributes = {
                    **email_attributes,
                    'phoneNumber': [email_request.phone_number],
                    'phoneType': ['whatsapp'],
                    'phoneVerified': ['yes'],
                    'verificationRoute': ['ngpt_wa']
                }

                # Update the email user's account with the phone number
                keycloak_admin.update_user(
                    user_id=email_user['id'],
                    payload={
                        "attributes": merged_attributes,
                        "email": email_request.email,
                        "emailVerified": True
                    }
                )

                # Disable the phone-only account as we've merged it
                keycloak_admin.update_user(
                    user_id=phone_user['id'],
                    payload={"enabled": False}
                )

                logger.info(f"Successfully merged accounts for phone {email_request.phone_number} and email {email_request.email}")

                # Get the updated user data
                updated_user = get_user_by_email_or_username(email_request.email)
                delete_temp_data(email_request.phone_number)

                return {
                    "message": "Accounts merged successfully",
                    "user": format_user_response(updated_user)
                }

            except KeycloakError as e:
                logger.error(f"Failed to merge accounts: {str(e)}")
                raise HTTPException(status_code=500, detail="Failed to merge accounts")

        elif phone_user:
            # Only phone user exists, add email to their account
            try:
                keycloak_admin = create_keycloak_admin()
                keycloak_admin.update_user(
                    user_id=phone_user['id'],
                    payload={
                        "email": email_request.email,
                        "emailVerified": False
                    }
                )
                updated_user = get_user_by_phone_or_username(email_request.phone_number)
                delete_temp_data(email_request.phone_number)
                return {
                    "message": "Email added to existing account",
                    "user": format_user_response(updated_user)
                }

            except KeycloakError as e:
                logger.error(f"Failed to update user email: {str(e)}")
                raise HTTPException(status_code=500, detail="Failed to update user email")

        elif email_user:
            # Only email user exists, add phone to their account
            result = add_phone_attributes_to_user(
                email_user['id'],
                email_request.phone_number,
                phone_type="whatsapp",
                phone_verified="yes",
                verification_route="ngpt_wa"
            )
            delete_temp_data(email_request.phone_number)
            return {
                "message": "Phone attributes added to existing account",
                "user": format_user_response(email_user)
            }

        else:
            # Neither user exists, proceed to create new account
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
    if rate_limiter.is_rate_limited(
        f"create_user:{user_data.phone_number}",
        limit=settings.rate_limit["create_user"]["limit"],
        period=settings.rate_limit["create_user"]["period"]
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

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
async def verify_email_route(verify_data: VerifyEmailRequest, api_key: str = Depends(get_api_key)):
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

        # If OTP is valid, mark the email as verified in Keycloak
        result = verify_email(verify_data.email)
        return {"message": "Email verified successfully."}
    except KeycloakOperationError as e:
        logger.error(f"Failed to verify email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify email")
    except Exception as e:
        logger.error(f"Error in verify_email_route: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")