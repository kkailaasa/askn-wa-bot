from pydantic_settings import BaseSettings
from typing import List
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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

    # Authorization
    API_KEY: str

    # FastAPI Configuration
    PORT: int

    # Celery Configuration
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL

    # Security Settings
    CORS_ALLOWED_ORIGINS: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Parse the string values into lists after initialization
        self.CORS_ALLOWED_ORIGINS = self._parse_list_from_env(self.CORS_ALLOWED_ORIGINS)

    @staticmethod
    def _parse_list_from_env(value: str) -> List[str]:
        logger.debug(f"Raw value: {value}")
        if not value:
            logger.warning("Value is not set or is empty")
            return []
        # Always treat the value as a comma-separated list
        parsed = [item.strip() for item in value.split(",") if item.strip()]
        logger.debug(f"Parsed value: {parsed}")
        return parsed

# Initialize settings outside of the class definition
try:
    settings = Settings()
    logger.debug(f"CORS Allowed Origins: {settings.CORS_ALLOWED_ORIGINS}")
    logger.debug(f"Port: {settings.PORT}")
except Exception as e:
    logger.error(f"Error initializing settings: {str(e)}")
    raise