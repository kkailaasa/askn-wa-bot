from pydantic_settings import BaseSettings
from typing import List
import os
import json

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
    PORT: str = "8000"

    # Celery Configuration
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL

    # Security Settings
    ALLOWED_DOMAINS: List[str] = []
    ALLOWED_IPS: List[str] = []
    TWILIO_IP_RANGES: List[str] = []

    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ALLOWED_DOMAINS = self._parse_list_from_env("ALLOWED_DOMAINS")
        self.ALLOWED_IPS = self._parse_list_from_env("ALLOWED_IPS")
        self.TWILIO_IP_RANGES = self._parse_list_from_env("TWILIO_IP_RANGES")

    @staticmethod
    def _parse_list_from_env(key: str) -> List[str]:
        value = os.getenv(key)
        logger.debug(f"Raw value for {key}: {value}")
        
        if not value:
            logger.warning(f"{key} is not set or is empty")
            return []
        
        try:
            # Try parsing as JSON first
            parsed = json.loads(value)
            logger.debug(f"Parsed {key} as JSON: {parsed}")
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            # If not JSON, split by comma and strip whitespace
            parsed = [item.strip() for item in value.split(",") if item.strip()]
            logger.debug(f"Parsed {key} as comma-separated list: {parsed}")
            return parsed

    def __getattribute__(self, item):
        value = super().__getattribute__(item)
        if isinstance(value, str):
            # Remove quotes from string values
            return value.strip("\"'")
        return value

settings = Settings()

logger.debug(f"Allowed Domains: {settings.ALLOWED_DOMAINS}")
logger.debug(f"Allowed IPs: {settings.ALLOWED_IPS}")
logger.debug(f"Twilio IP Ranges: {settings.TWILIO_IP_RANGES}")