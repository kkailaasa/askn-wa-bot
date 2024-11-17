# core/config.py

from pydantic_settings import BaseSettings
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import logging
from enum import Enum
from datetime import timedelta
from pydantic import validator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnvironmentType(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class SequenceSettings(BaseSettings):
    """Configuration for sequence management"""
    SEQUENCE_EXPIRY: int = 3600  # 1 hour
    SEQUENCE_LOCK_TIMEOUT: int = 30  # 30 seconds
    MAX_STEP_RETRIES: int = 3
    STEP_RETRY_DELAY: float = 0.1  # 100ms
    CLEANUP_INTERVAL: int = 3600  # 1 hour
    MAX_CONCURRENT_OPERATIONS: int = 100
    TRANSACTION_TIMEOUT: int = 10  # 10 seconds

class TimeoutSettings(BaseSettings):
    """Timeout configurations"""
    REDIS_OPERATION_TIMEOUT: int = 5
    KEYCLOAK_OPERATION_TIMEOUT: int = 10
    EMAIL_OPERATION_TIMEOUT: int = 15
    SEQUENCE_VALIDATION_TIMEOUT: int = 5
    LOCK_ACQUISITION_TIMEOUT: int = 5
    DEFAULT_OPERATION_TIMEOUT: int = 10

class RateLimitSettings(BaseSettings):
    """Enhanced rate limit configurations"""
    # Sequence Operations
    SEQUENCE_OPERATIONS_LIMIT: int = 100
    SEQUENCE_OPERATIONS_PERIOD: int = 60  # per minute

    # Step Transitions
    STEP_TRANSITION_LIMIT: int = 20
    STEP_TRANSITION_PERIOD: int = 60  # per minute

    # Data Validations
    DATA_VALIDATION_LIMIT: int = 50
    DATA_VALIDATION_PERIOD: int = 60  # per minute

class Settings(BaseSettings):
    """Main configuration class with enhanced settings"""
    # Environment Configuration
    ENVIRONMENT: EnvironmentType = EnvironmentType.DEVELOPMENT
    DEBUG: bool = False

    # Application Configuration
    APP_NAME: str = "E-Citizen WhatsApp Bot"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8000

    # Security Settings
    API_KEY: str
    CORS_ALLOWED_ORIGINS: str = ""
    MAX_REQUEST_SIZE: int = 1024 * 1024  # 1MB

    # Sequence Management Settings
    SEQUENCE: SequenceSettings = SequenceSettings()
    TIMEOUTS: TimeoutSettings = TimeoutSettings()

    # Redis Configuration
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_MAX_CONNECTIONS: int = 20
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 2
    REDIS_MAX_RETRIES: int = 3
    REDIS_URL: Optional[str] = None
    REDIS_POOL_SIZE: int = 20
    REDIS_CONNECTION_RETRIES: int = 3
    REDIS_RETRY_DELAY: float = 0.1

    # Enhanced Rate Limiting Configuration
    RATE_LIMITS: RateLimitSettings = RateLimitSettings()

    # User Creation Rate Limits
    RATE_LIMIT_CREATE_USER_LIMIT: int = 5
    RATE_LIMIT_CREATE_USER_PERIOD: int = 3600  # 1 hour

    # Email Management Rate Limits
    RATE_LIMIT_ADD_EMAIL_LIMIT: int = 3
    RATE_LIMIT_ADD_EMAIL_PERIOD: int = 3600  # 1 hour

    # Email Verification Rate Limits
    RATE_LIMIT_VERIFY_EMAIL_LIMIT: int = 5
    RATE_LIMIT_VERIFY_EMAIL_PERIOD: int = 300  # 5 minutes

    # Message Rate Limiting
    MESSAGE_RATE_LIMIT: int = 5
    MESSAGE_RATE_WINDOW: int = 300  # 5 minutes

    # New Rate Limit Settings
    RATE_LIMIT_CHECK_PHONE_LIMIT: int = 10
    RATE_LIMIT_CHECK_PHONE_PERIOD: int = 300  # 5 minutes
    RATE_LIMIT_SEND_OTP_LIMIT: int = 3
    RATE_LIMIT_SEND_OTP_PERIOD: int = 300  # 5 minutes
    RATE_LIMIT_USER_INFO_LIMIT: int = 20
    RATE_LIMIT_USER_INFO_PERIOD: int = 300  # 5 minutes
    RATE_LIMIT_SIGNUP_LIMIT: int = 10
    RATE_LIMIT_SIGNUP_PERIOD: int = 60  # 1 minute
    RATE_LIMIT_LOAD_STATS_LIMIT: int = 30
    RATE_LIMIT_LOAD_STATS_PERIOD: int = 60  # 1 minute

    # Twilio Configuration
    TWILIO_NUMBERS: str = ""
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str

    # Keycloak Configuration
    KEYCLOAK_SERVER_URL: str
    KEYCLOAK_API_CLIENT_ID: str
    KEYCLOAK_REALM: str
    KEYCLOAK_USER_NAME: str
    KEYCLOAK_PASSWORD: str
    KEYCLOAK_CACHE_EXPIRATION: int = 3600
    KEYCLOAK_TIMEOUT: int = 10
    KEYCLOAK_MAX_RETRIES: int = 3
    KEYCLOAK_RETRY_DELAY: float = 0.1

    # Database Configuration
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "an_wa_bot"
    DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_MAX_OVERFLOW: int = 10
    DB_CONNECTION_RETRIES: int = 3
    DB_RETRY_DELAY: float = 0.1

    # Sendgrid Configuration
    SENDGRID_API_KEY: str
    EMAIL_FROM_NAME: str
    EMAIL_FROM: str

    # Add Celery Configuration
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # Celery Task Settings
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: List[str] = ["json"]
    CELERY_TIMEZONE: str = "UTC"
    CELERY_ENABLE_UTC: bool = True
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_TIME_LIMIT: int = 30 * 60  # 30 minutes
    CELERY_TASK_SOFT_TIME_LIMIT: int = 25 * 60  # 25 minutes
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1
    CELERY_WORKER_MAX_TASKS_PER_CHILD: int = 50
    CELERY_WORKER_MAX_MEMORY_PER_CHILD: int = 100_000  # 100MB

    # Enhanced Error Handling Settings
    ERROR_RETRY_ATTEMPTS: int = 3
    ERROR_RETRY_DELAY: float = 0.1
    ERROR_LOGGING_LEVEL: str = "ERROR"
    DETAILED_ERROR_RESPONSES: bool = True  # Set to True only in development

    @validator('TWILIO_NUMBERS', pre=True)
    def parse_twilio_numbers(cls, value):
        if isinstance(value, str):
            return value
        return ""

    @property
    def rate_limit_config(self) -> Dict[str, Dict[str, Any]]:
        """Enhanced rate limit configuration"""
        return {
            # Sequence Operations
            "sequence_operations": {
                "limit": self.RATE_LIMITS.SEQUENCE_OPERATIONS_LIMIT,
                "period": self.RATE_LIMITS.SEQUENCE_OPERATIONS_PERIOD,
                "key_pattern": "rate_limit:sequence:{identifier}",
                "identifier_type": "identifier"
            },
            # Message Rate Limits
            "message": {
                "limit": self.MESSAGE_RATE_LIMIT,
                "period": self.MESSAGE_RATE_WINDOW,
                "key_pattern": "rate_limit:message:{phone_number}",
                "identifier_type": "phone_number"
            },
            # Account Creation Rate Limits
            "create_user": {
                "limit": self.RATE_LIMIT_CREATE_USER_LIMIT,
                "period": self.RATE_LIMIT_CREATE_USER_PERIOD,
                "key_pattern": "rate_limit:create_user:{phone_number}",
                "identifier_type": "phone_number"
            },
            # Email Management Rate Limits
            "add_email": {
                "limit": self.RATE_LIMIT_ADD_EMAIL_LIMIT,
                "period": self.RATE_LIMIT_ADD_EMAIL_PERIOD,
                "key_pattern": "rate_limit:add_email:{email}",
                "identifier_type": "email"
            },
            # Step Transition Rate Limits
            "step_transition": {
                "limit": self.RATE_LIMITS.STEP_TRANSITION_LIMIT,
                "period": self.RATE_LIMITS.STEP_TRANSITION_PERIOD,
                "key_pattern": "rate_limit:step:{identifier}",
                "identifier_type": "identifier"
            }
        }

class TimeoutSettings(BaseSettings):
    """Timeout configurations"""
    CHAT_TIMEOUT: int = 15
    AUTH_TIMEOUT: int = 10
    SEQUENCE_TIMEOUT: int = 5
    EMAIL_TIMEOUT: int = 10
    CACHE_TIMEOUT: int = 3
    HEALTH_CHECK_TIMEOUT: int = 2
    OPERATION_TIMEOUT: int = 10

    # Add timeout settings
    TIMEOUTS: TimeoutSettings = TimeoutSettings()

    # Add request tracking settings
    REQUEST_TRACKING_ENABLED: bool = True
    REQUEST_ID_HEADER: str = "X-Request-ID"
    PROPAGATE_REQUEST_ID: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_dynamic_settings()
        self._validate_settings()

    def _init_dynamic_settings(self) -> None:
        """Initialize settings that depend on other settings"""
        # Set Redis URL if not provided
        self.REDIS_URL = self.REDIS_URL or f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

        # Set Database URL if not provided
        if not hasattr(self, 'DATABASE_URL') or not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@db:5432/{self.POSTGRES_DB}"
            )

        # Set Database URL if not provided
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@db:5432/{self.POSTGRES_DB}"
            )

        # Parse CORS origins
        self.CORS_ALLOWED_ORIGINS = self._parse_cors_origins()

        # Set Celery URLs if not provided
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.CELERY_BROKER_URL


    def _validate_settings(self) -> None:
        """Validate critical settings"""
        try:
            # Validate Database URL
            result = urlparse(self.DATABASE_URL)
            if not all([result.scheme, result.netloc]):
                raise ValueError("Invalid DATABASE_URL")

            # Validate Redis URL
            redis_result = urlparse(self.REDIS_URL)
            if not all([redis_result.scheme, redis_result.netloc]):
                raise ValueError("Invalid REDIS_URL")

            # Validate critical settings presence
            critical_settings = [
                "TWILIO_ACCOUNT_SID",
                "TWILIO_AUTH_TOKEN",
                "DIFY_KEY",
                "KEYCLOAK_SERVER_URL",
                "API_KEY",
                "POSTGRES_PASSWORD"
            ]

            missing = [key for key in critical_settings if not getattr(self, key, None)]
            if missing:
                raise ValueError(f"Missing critical settings: {', '.join(missing)}")

            # Validate timeout settings
            if self.SEQUENCE.SEQUENCE_LOCK_TIMEOUT >= self.SEQUENCE.SEQUENCE_EXPIRY:
                raise ValueError("Lock timeout must be less than sequence expiry")

        except Exception as e:
            logger.error(f"Configuration validation failed: {str(e)}")
            raise

    def _parse_cors_origins(self) -> List[str]:
        """Parse CORS origins from string to list"""
        if not self.CORS_ALLOWED_ORIGINS:
            return []
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

# Initialize settings
try:
    settings = Settings()
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.debug(f"CORS Allowed Origins: {settings.CORS_ALLOWED_ORIGINS}")
    logger.debug(f"Rate Limit Config: {settings.rate_limit_config}")
except Exception as e:
    logger.error(f"Error initializing settings: {str(e)}")
    raise