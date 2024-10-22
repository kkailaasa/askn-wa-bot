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
    logger.debug(f"Received message - From: {From}, Body: {Body}")

    # Validate the request is from Twilio
    #await validate_twilio_request(request)

    # Clean up the phone number format
    phone_number = From
    if not phone_number.startswith("whatsapp:"):
        phone_number = f"whatsapp:{From}"

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

    try:
        # Initialize services
        chat_service = None
        messaging_service = None

        try:
            chat_service = ChatService()
            messaging_service = MessagingService()
        except Exception as init_error:
            logger.error(f"Error initializing services: {str(init_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to initialize messaging services"
            )

        # Get or create conversation ID
        try:
            logger.debug("Getting conversation ID")
            conversation_id = chat_service.get_conversation_id(phone_number)
            logger.debug(f"Conversation ID: {conversation_id}")
        except Exception as conv_error:
            logger.error(f"Error getting conversation ID: {str(conv_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to get conversation"
            )

        # Get response from chat service
        try:
            logger.debug("Creating chat message")
            response = chat_service.create_chat_message(
                user=phone_number,
                query=Body,
                conversation_id=conversation_id
            )
            logger.debug(f"Generated response: {response}")
        except Exception as chat_error:
            logger.error(f"Error generating response: {str(chat_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to generate response"
            )

        # Send response back to user
        try:
            logger.debug("Sending message back to user")
            messaging_service.send_message(phone_number, response)
        except Exception as send_error:
            logger.error(f"Error sending message: {str(send_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to send message"
            )

        return JSONResponse(
            content={"message": "Message processed successfully."},
            status_code=200
        )

    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        logger.error(f"Unexpected error processing message: {str(e)}", exc_info=True)

        # Try to send error message to user
        if messaging_service:
            try:
                messaging_service.send_message(
                    phone_number,
                    "Sorry, an error occurred while processing your message. Please try again later."
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message: {str(send_error)}", exc_info=True)

        return JSONResponse(
            content={"message": "An unexpected error occurred while processing your message."},
            status_code=500
        )

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
            # If user exists but has no email, store temp data and proceed to check_email
            if not user.get('email'):
                store_temp_data(phone_request.phone_number, {
                    "phone_number": phone_request.phone_number,
                    "user_id": user.get('id')  # Store the user ID for later use
                })
                return {
                    "message": "User found but email not set",
                    "user": user,
                    "next_step": "check_email"
                }
            return {"message": "User found", "user": user}
        else:
            store_temp_data(phone_request.phone_number, {"phone_number": phone_request.phone_number})
            return {"message": "User not found", "next_step": "check_email"}
    except KeycloakOperationError as e:
        logger.error(f"Keycloak operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

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
                    "user": updated_user
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
                return {"message": "Email added to existing account", "user": updated_user}

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
            return {"message": "Phone attributes added to existing account", "user": email_user}

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