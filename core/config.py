from pydantic_settings import BaseSettings
from typing import List, Dict
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class RateLimitConfig(BaseSettings):
    create_user: Dict[str, int] = {"limit": 5, "period": 3600}
    add_email: Dict[str, int] = {"limit": 3, "period": 3600}
    verify_email: Dict[str, int] = {"limit": 5, "period": 300}

class Settings(BaseSettings):
    # Twilio Configuration
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_NUMBER: str

    # Dify Configuration
    DIFY_KEY: str
    DIFY_URL: str

    # Keycloak Configuration
    KEYCLOAK_SERVER_URL: str
    KEYCLOAK_API_CLIENT_ID: str
    KEYCLOAK_REALM: str
    KEYCLOAK_USER_NAME: str
    KEYCLOAK_PASSWORD: str

    # Redis Configuration
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
    REDIS_MAX_CONNECTIONS: int = 10

    # Message Rate Limiting Configuration
    MESSAGE_RATE_LIMIT: int = 2
    MESSAGE_RATE_WINDOW: int = 60

    # setting for cache expiration time (in seconds)
    KEYCLOAK_CACHE_EXPIRATION: str

    # Authorization
    API_KEY: str

    # Rate Limiting Configuration
    RATE_LIMIT: RateLimitConfig = RateLimitConfig()

    # FastAPI Configuration
    PORT: int = 8000

    # Celery Configuration
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL

    # Security Settings
    CORS_ALLOWED_ORIGINS: str = ""

    # Email Configuration
    SENDGRID_API_KEY: str
    EMAIL_FROM_NAME: str
    EMAIL_FROM: str

    class Config:
        env_file = ".env"
        case_sensitive = True
        env_prefix = ""
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.CORS_ALLOWED_ORIGINS = self._parse_list_from_env(self.CORS_ALLOWED_ORIGINS)

    @staticmethod
    def _parse_list_from_env(value: str) -> List[str]:
        logger.debug(f"Raw value: {value}")
        if not value:
            logger.warning("Value is not set or is empty")
            return []
        parsed = [item.strip() for item in value.split(",") if item.strip()]
        logger.debug(f"Parsed value: {parsed}")
        return parsed

# Initialize settings
try:
    settings = Settings()
    logger.debug(f"CORS Allowed Origins: {settings.CORS_ALLOWED_ORIGINS}")
    logger.debug(f"FastAPI Port: {settings.PORT}")
    logger.debug(f"Rate Limit Config: {settings.RATE_LIMIT}")
    logger.debug(f"Message Rate Limit: {settings.MESSAGE_RATE_LIMIT}")
    logger.debug(f"Message Rate Window: {settings.MESSAGE_RATE_WINDOW}")
except Exception as e:
    logger.error(f"Error initializing settings: {str(e)}")
    raise