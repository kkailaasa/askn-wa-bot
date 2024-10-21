from pydantic_settings import BaseSettings
from typing import List, Dict
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class RateLimitConfig(BaseSettings):
    create_user: Dict[str, int] = {"limit": 5, "period": 3600}
    add_email: Dict[str, int] = {"limit": 3, "period": 3600}
    verify_email: Dict[str, int] = {"limit": 5, "period": 300}

    class Config:
        env_file = ".env"
        env_prefix = "RATE_LIMIT__"
        env_nested_delimiter = "__"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Map environment variables to dictionary structure
        self.create_user = {
            "limit": self._get_env_int("CREATE_USER__LIMIT", 5),
            "period": self._get_env_int("CREATE_USER__PERIOD", 3600)
        }
        self.add_email = {
            "limit": self._get_env_int("ADD_EMAIL__LIMIT", 3),
            "period": self._get_env_int("ADD_EMAIL__PERIOD", 3600)
        }
        self.verify_email = {
            "limit": self._get_env_int("VERIFY_EMAIL__LIMIT", 5),
            "period": self._get_env_int("VERIFY_EMAIL__PERIOD", 300)
        }

    def _get_env_int(self, key: str, default: int) -> int:
        """Helper method to get integer values from environment variables"""
        import os
        full_key = f"RATE_LIMIT__{key}"
        value = os.getenv(full_key)
        try:
            return int(value) if value is not None else default
        except ValueError:
            logger.warning(f"Invalid value for {full_key}, using default: {default}")
            return default

class Settings(BaseSettings):
    # ... [previous settings remain the same]

    # Message Rate Limiting Configuration
    MESSAGE_RATE_LIMIT: int = 2  # Conservative default: 2 messages
    MESSAGE_RATE_WINDOW: int = 60  # Conservative default: 1 minute window

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