from fastapi import APIRouter, Form, HTTPException, Depends, Request
from tasks.celery_tasks import process_question
from services.ecitizen_auth import get_user_by_email, get_user_by_phone
from services.auth import get_api_key
from utils.twilio_validator import validate_twilio_request
from typing import Optional
from pydantic import BaseModel, EmailStr

router = APIRouter()

class EmailRequest(BaseModel):
    email: EmailStr

class PhoneRequest(BaseModel):
    phone_number: str

class UserResponse(BaseModel):
    email: str
    enabled: bool
    phoneType: Optional[str]
    phoneNumber: Optional[str]
    gender: Optional[str]
    phoneNumberVerified: Optional[bool]
    firstName: str
    lastName: str

@router.post("/message")
async def reply(request: Request, Body: str = Form(), From: str = Form()):
    # WARNING: Twilio request validation is currently disabled. 
    # await validate_twilio_request(request)
    
    process_question.delay(Body, From)
    return {"status": "Task added"}

@router.post("/get_user_by_email", response_model=UserResponse)
async def get_user_email(email_request: EmailRequest, api_key: str = Depends(get_api_key)):
    user_info = get_user_by_email(email_request.email)
    if user_info:
        return UserResponse(**user_info)
    else:
        raise HTTPException(status_code=404, detail="User not found")

@router.post("/get_user_by_phone", response_model=UserResponse)
async def get_user_phone(phone_request: PhoneRequest, api_key: str = Depends(get_api_key)):
    user_info = get_user_by_phone(phone_request.phone_number)
    if user_info:
        return UserResponse(**user_info)
    else:
        raise HTTPException(status_code=404, detail="User not found")