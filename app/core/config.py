# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "KAILASA AI WhatsApp Bot"
    DEBUG: bool = False
    API_KEY: str

    # Twilio Settings
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_NUMBERS: list[str]

    # Dify Settings
    DIFY_KEY: str
    DIFY_URL: str

    # Load Balancer Settings
    LOAD_BALANCER_HIGH_THRESHOLD: float = 0.7
    LOAD_BALANCER_ALERT_THRESHOLD: float = 0.9

    # Mattermost Settings
    MATTERMOST_WEBHOOK_URL: str

    class Config:
        env_file = ".env"

settings = Settings()