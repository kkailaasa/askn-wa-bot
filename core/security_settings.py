from typing import List, Optional
from pydantic_settings import BaseSettings
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class SecuritySettings(BaseSettings):
    ALLOWED_DOMAINS: Optional[str] = ""
    ALLOWED_IPS: Optional[str] = ""
    TWILIO_IP_RANGES: Optional[str] = ""
    
    # Additional fields
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_NUMBER: str
    DIFY_KEY: str
    DIFY_URL: str
    KEYCLOAK_SERVER_URL: str
    KEYCLOAK_API_CLIENT_ID: str
    KEYCLOAK_REALM: str
    KEYCLOAK_USER_NAME: str
    KEYCLOAK_PASSWORD: str
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_URL: str
    API_KEY: str
    PORT: int
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    CORS_ALLOWED_ORIGINS: Optional[str] = ""

    class Config:
        env_file = ".env"

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

try:
    security_settings = SecuritySettings()
    logger.debug(f"CORS Allowed Origins: {security_settings.CORS_ALLOWED_ORIGINS}")
except Exception as e:
    logger.error(f"Error initializing settings: {str(e)}")
    raise