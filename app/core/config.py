# app/core/config.py
from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # Application Settings
    APP_NAME: str = "E-Citizen WhatsApp Bot"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    API_KEY: str

    # Database Settings
    DB_PATH: str = "app/data/app.db"

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

    # Rate Limiting
    RATE_LIMIT_LOAD_STATS_LIMIT: int = 100
    RATE_LIMIT_LOAD_STATS_PERIOD: int = 3600

    def get_twilio_numbers(self) -> List[str]:
        """Convert comma-separated string to list of numbers"""
        if not self.TWILIO_NUMBERS:
            return []
        return [num.strip() for num in self.TWILIO_NUMBERS.split(',')]

    @property
    def database_url(self) -> str:
        """Get SQLite database URL"""
        return f"sqlite:///{self.DB_PATH}"

    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings(
    _env_file=os.getenv('ENV_FILE', '.env'),  # Allow env file override
)