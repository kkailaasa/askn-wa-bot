from pydantic_settings import BaseSettings

class Settings(BaseSettings):
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
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    class Config:
        env_file = ".env"

settings = Settings()