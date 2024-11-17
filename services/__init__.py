# services/__init__.py
from .rate_limiter import RateLimiter
from .dify_chat import ChatService
from .twilio_auth import MessagingService
from .email_service import EmailService
from .ecitizen_auth import ECitizenAuthService, auth_service

from .ecitizen_auth import (
    get_user_by_email_or_username,
    get_user_by_phone_or_username,
    create_user_with_phone,
    add_phone_attributes_to_user,
    verify_email,
    generate_otp,
    store_otp,
    verify_otp,
    store_temp_data,
    get_temp_data,
    delete_temp_data
)

from .sequence_manager import (
    sequence_manager,
    AccountCreationStep,
    SequenceManager,
    TransactionManager,
    STEP_VALIDATORS
)

# Create an instance of the auth service
class EcitzenAuthService:
    def __init__(self):
        self.create_keycloak_admin = create_keycloak_admin
        self.get_user_by_email_or_username = get_user_by_email_or_username
        self.get_user_by_phone_or_username = get_user_by_phone_or_username
        self.create_user_with_phone = create_user_with_phone
        self.add_phone_attributes_to_user = add_phone_attributes_to_user
        self.verify_email = verify_email
        self.generate_otp = generate_otp
        self.store_otp = store_otp
        self.verify_otp = verify_otp
        self.store_temp_data = store_temp_data
        self.get_temp_data = get_temp_data
        self.delete_temp_data = delete_temp_data

# List all public exports
__all__ = [
    # Services
    'ChatService',
    'MessagingService',
    'EcitzenAuthService',

    # Sequence Management__all__ = [
    'ChatService',
    'MessagingService',
    'ECitizenAuthService',
    'auth_service',
    'EmailService',
    'sequence_manager',
    'AccountCreationStep',
    'SequenceManager',
    'TransactionManager',
    'STEP_VALIDATORS',
    'RateLimiter'
]