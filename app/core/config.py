# app/core/config.py
from pydantic_settings import BaseSettings
from typing import List, Optional
import os

class Settings(BaseSettings):
    # Application Settings
    APP_NAME: str = "E-Citizen WhatsApp Bot"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    API_KEY: str
    ENVIRONMENT: str = "development"

    # CORS Settings
    CORS_ALLOWED_ORIGINS: str = "https://hono.koogle.sk,https://api.twilio.com"

    # Request Settings
    MAX_REQUEST_SIZE: int = 1048576

    # Database Settings
    DB_PATH: str = "app/data/app.db"
    DATABASE_URL: Optional[str] = None

    # Redis Configuration
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_MAX_CONNECTIONS: int = 10
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 2
    REDIS_MAX_RETRIES: int = 3
    REDIS_PASSWORD: str = ""

    # Twilio Settings
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_NUMBERS: str  # Comma-separated string of numbers
    TWILIO_MAX_CONNECTIONS: int = 10

    # Dify Settings
    DIFY_KEY: str
    DIFY_URL: str
    DIFY_MAX_CONNECTIONS: int = 10
    DIFY_TIMEOUT: int = 15

    # Load Balancer Settings
    LOAD_BALANCER_HIGH_THRESHOLD: float = 0.7
    LOAD_BALANCER_ALERT_THRESHOLD: float = 0.9
    MAX_MESSAGES_PER_SECOND: int = 70
    LOAD_BALANCER_STATS_WINDOW: int = 60

    # Rate Limiting Settings
    RATE_LIMIT_LOAD_STATS_LIMIT: int = 100
    RATE_LIMIT_LOAD_STATS_PERIOD: int = 3600
    RATE_LIMIT_CHECK_PHONE_LIMIT: int = 5000
    RATE_LIMIT_CHECK_PHONE_PERIOD: int = 300
    RATE_LIMIT_SEND_OTP_LIMIT: int = 3
    RATE_LIMIT_SEND_OTP_PERIOD: int = 300
    RATE_LIMIT_USER_INFO_LIMIT: int = 500
    RATE_LIMIT_USER_INFO_PERIOD: int = 300
    RATE_LIMIT_SIGNUP_LIMIT: int = 5000
    RATE_LIMIT_SIGNUP_PERIOD: int = 60

    # Keycloak Settings
    KEYCLOAK_SERVER_URL: str
    KEYCLOAK_REALM: str = "epassport"
    KEYCLOAK_API_CLIENT_ID: str = "admin-cli"
    KEYCLOAK_USER_NAME: str = "admin"
    KEYCLOAK_PASSWORD: str
    KEYCLOAK_CACHE_EXPIRATION: int = 3600
    KEYCLOAK_TIMEOUT: int = 10

    # Database Pool Settings
    DB_POOL_SIZE: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_MAX_OVERFLOW: int = 10

    # HTTP Settings
    HTTP_POOL_MAX_SIZE: int = 100
    HTTP_POOL_TIMEOUT: int = 30

    # Email Settings
    SENDGRID_API_KEY: Optional[str] = None
    EMAIL_FROM_NAME: Optional[str] = None
    EMAIL_FROM: Optional[str] = None

    # Mattermost Settings
    MATTERMOST_WEBHOOK_URL: Optional[str] = None

    def get_twilio_numbers(self) -> List[str]:
        """Convert comma-separated string to list of numbers"""
        if not self.TWILIO_NUMBERS:
            return []
        return [num.strip() for num in self.TWILIO_NUMBERS.split(',')]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # This will ignore extra fields instead of raising errors

# Create settings instance
settings = Settings(
    _env_file=os.getenv('ENV_FILE', '.env'),
)