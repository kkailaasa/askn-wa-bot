# core/sequence_errors.py

from enum import Enum
from typing import Dict, Any, Optional, Union
from fastapi import HTTPException
import json
from datetime import datetime
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class SequenceStatus(str, Enum):
    """Enhanced status enumeration for sequence operations"""
    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"
    BLOCKED = "blocked"
    RETRY_NEEDED = "retry_needed"
    LOCKED = "locked"
    INVALID = "invalid"
    EXPIRED = "expired"

class SequenceErrorCode(str, Enum):
    """Comprehensive error codes for sequence operations"""
    # Validation Errors
    INVALID_PHONE = "INVALID_PHONE"
    INVALID_EMAIL = "INVALID_EMAIL"
    INVALID_DATA = "INVALID_DATA"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    
    # Sequence State Errors
    SEQUENCE_VIOLATION = "SEQUENCE_VIOLATION"
    SEQUENCE_EXPIRED = "SEQUENCE_EXPIRED"
    SEQUENCE_BLOCKED = "SEQUENCE_BLOCKED"
    SEQUENCE_LOCKED = "SEQUENCE_LOCKED"
    SEQUENCE_NOT_FOUND = "SEQUENCE_NOT_FOUND"
    INVALID_STEP_TRANSITION = "INVALID_STEP_TRANSITION"
    
    # Transaction Errors
    TRANSACTION_FAILED = "TRANSACTION_FAILED"
    LOCK_ACQUISITION_FAILED = "LOCK_ACQUISITION_FAILED"
    CONCURRENT_MODIFICATION = "CONCURRENT_MODIFICATION"
    
    # Service Errors
    KEYCLOAK_ERROR = "KEYCLOAK_ERROR"
    REDIS_ERROR = "REDIS_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    EMAIL_ERROR = "EMAIL_ERROR"
    TWILIO_ERROR = "TWILIO_ERROR"
    DIFY_ERROR = "DIFY_ERROR"
    
    # Data Errors
    DATA_MISMATCH = "DATA_MISMATCH"
    DATA_NOT_FOUND = "DATA_NOT_FOUND"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    INVALID_FORMAT = "INVALID_FORMAT"
    
    # State Errors
    ACCOUNT_EXISTS = "ACCOUNT_EXISTS"
    EMAIL_EXISTS = "EMAIL_EXISTS"
    PHONE_EXISTS = "PHONE_EXISTS"
    
    # System Errors
    SYSTEM_ERROR = "SYSTEM_ERROR"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"

class ErrorContext(BaseModel):
    """Structured error context for better error tracking"""
    timestamp: str
    error_code: SequenceErrorCode
    message: str
    details: Optional[Dict[str, Any]] = None
    retry_count: Optional[int] = None
    operation: Optional[str] = None
    sequence_state: Optional[Dict[str, Any]] = None

class SequenceResponse(BaseModel):
    """Enhanced response model with detailed status information"""
    status: SequenceStatus
    message: str
    error_code: Optional[SequenceErrorCode] = None
    data: Optional[Dict[str, Any]] = None
    next_action: Optional[str] = None
    retry_after: Optional[int] = None
    error_context: Optional[ErrorContext] = None

    class Config:
        use_enum_values = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary with all relevant information"""
        response = {
            "status": self.status,
            "message": self.message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if self.error_code:
            response["error_code"] = self.error_code
        if self.data:
            response["data"] = self.data
        if self.next_action:
            response["next_action"] = self.next_action
        if self.retry_after:
            response["retry_after"] = self.retry_after
        if self.error_context:
            response["error_context"] = self.error_context.dict()
            
        return response

    @classmethod
    def success(cls, message: str, data: Optional[Dict[str, Any]] = None, next_action: Optional[str] = None) -> 'SequenceResponse':
        """Create a success response"""
        return cls(
            status=SequenceStatus.SUCCESS,
            message=message,
            data=data,
            next_action=next_action
        )

    @classmethod
    def failure(
        cls, 
        message: str, 
        error_code: SequenceErrorCode, 
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None,
        operation: Optional[str] = None
    ) -> 'SequenceResponse':
        """Create a detailed failure response"""
        error_context = ErrorContext(
            timestamp=datetime.utcnow().isoformat(),
            error_code=error_code,
            message=message,
            details=details,
            operation=operation
        )
        
        return cls(
            status=SequenceStatus.FAILED,
            message=message,
            error_code=error_code,
            retry_after=retry_after,
            error_context=error_context
        )

    @classmethod
    def pending(cls, message: str, next_action: str) -> 'SequenceResponse':
        """Create a pending response"""
        return cls(
            status=SequenceStatus.PENDING,
            message=message,
            next_action=next_action
        )

    @classmethod
    def blocked(cls, message: str, retry_after: int) -> 'SequenceResponse':
        """Create a blocked response"""
        return cls(
            status=SequenceStatus.BLOCKED,
            message=message,
            retry_after=retry_after
        )

    @classmethod
    def retry(cls, message: str, retry_after: int, error_code: SequenceErrorCode) -> 'SequenceResponse':
        """Create a retry response"""
        return cls(
            status=SequenceStatus.RETRY_NEEDED,
            message=message,
            retry_after=retry_after,
            error_code=error_code
        )

    @classmethod
    def user_friendly_message(cls, error_code: SequenceErrorCode) -> str:
        """Returns user-friendly messages for error codes"""
        messages = {
            # Validation Errors
            SequenceErrorCode.INVALID_PHONE: "The phone number provided is not valid. Please check and try again.",
            SequenceErrorCode.INVALID_EMAIL: "The email address provided is not valid. Please check and try again.",
            SequenceErrorCode.VALIDATION_ERROR: "Please check the information provided and try again.",
            
            # Sequence Errors
            SequenceErrorCode.SEQUENCE_VIOLATION: "There was an issue with the order of operations. Let's start over.",
            SequenceErrorCode.SEQUENCE_EXPIRED: "Your session has expired. Please start the process again.",
            SequenceErrorCode.SEQUENCE_BLOCKED: "The service is temporarily unavailable. Please try again in a few minutes.",
            SequenceErrorCode.SEQUENCE_LOCKED: "Another operation is in progress. Please wait a moment and try again.",
            
            # Transaction Errors
            SequenceErrorCode.TRANSACTION_FAILED: "The operation couldn't be completed. Please try again.",
            SequenceErrorCode.LOCK_ACQUISITION_FAILED: "The system is busy. Please try again in a moment.",
            SequenceErrorCode.CONCURRENT_MODIFICATION: "Someone else modified the data. Please refresh and try again.",
            
            # Service Errors
            SequenceErrorCode.KEYCLOAK_ERROR: "We're having trouble verifying your information. Please try again later.",
            SequenceErrorCode.REDIS_ERROR: "The service is temporarily unavailable. Please try again shortly.",
            SequenceErrorCode.RATE_LIMIT: "You've made too many requests. Please wait a moment before trying again.",
            SequenceErrorCode.EMAIL_ERROR: "We're having trouble sending the email. Please try again later.",
            
            # Data Errors
            SequenceErrorCode.DATA_NOT_FOUND: "We couldn't find your information. Please start the process again.",
            SequenceErrorCode.DATA_CORRUPTION: "There was an issue with your data. Please try again.",
            
            # State Errors
            SequenceErrorCode.ACCOUNT_EXISTS: "An account with this information already exists.",
            SequenceErrorCode.EMAIL_EXISTS: "This email is already registered.",
            SequenceErrorCode.PHONE_EXISTS: "This phone number is already registered.",
            
            # System Errors
            SequenceErrorCode.SYSTEM_ERROR: "We're experiencing technical difficulties. Please try again later.",
            SequenceErrorCode.TIMEOUT: "The operation timed out. Please try again.",
            SequenceErrorCode.NETWORK_ERROR: "There seems to be a network issue. Please check your connection and try again."
        }
        return messages.get(error_code, "An unexpected error occurred. Please try again later.")

class SequenceException(HTTPException):
    """Enhanced exception class with detailed error information"""
    def __init__(
        self,
        error_code: SequenceErrorCode,
        message: str,
        status_code: int = 400,
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        operation: Optional[str] = None
    ):
        self.error_code = error_code
        self.retry_after = retry_after
        self.operation = operation
        
        # Create error context
        error_context = ErrorContext(
            timestamp=datetime.utcnow().isoformat(),
            error_code=error_code,
            message=message,
            details=details,
            operation=operation
        )
        
        # Log the error
        logger.error(
            f"Sequence error occurred: {error_code}",
            extra={
                "error_context": error_context.dict(),
                "status_code": status_code
            }
        )
        
        super().__init__(
            status_code=status_code,
            detail=SequenceResponse.failure(
                message=message,
                error_code=error_code,
                details=details,
                retry_after=retry_after,
                operation=operation
            ).dict()
        )

# Helper function for error handling
def handle_sequence_error(
    error: Exception,
    operation: str,
    details: Optional[Dict[str, Any]] = None
) -> SequenceException:
    """Convert various exceptions to SequenceException with appropriate error codes"""
    if isinstance(error, SequenceException):
        return error
        
    error_mapping = {
        "ValidationError": (SequenceErrorCode.VALIDATION_ERROR, 400),
        "WatchError": (SequenceErrorCode.CONCURRENT_MODIFICATION, 409),
        "LockError": (SequenceErrorCode.LOCK_ACQUISITION_FAILED, 423),
        "TimeoutError": (SequenceErrorCode.TIMEOUT, 504),
        "RedisError": (SequenceErrorCode.REDIS_ERROR, 503),
        "KeycloakError": (SequenceErrorCode.KEYCLOAK_ERROR, 502),
    }
    
    error_type = type(error).__name__
    error_code, status_code = error_mapping.get(
        error_type, 
        (SequenceErrorCode.SYSTEM_ERROR, 500)
    )
    
    return SequenceException(
        error_code=error_code,
        message=str(error),
        status_code=status_code,
        details=details,
        operation=operation
    )

__all__ = [
    'SequenceStatus',
    'SequenceErrorCode',
    'SequenceResponse',
    'SequenceException',
    'ErrorContext',
    'handle_sequence_error'
]