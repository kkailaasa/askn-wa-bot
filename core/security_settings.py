from typing import List
from pydantic_settings import BaseSettings
import ipaddress
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class SecuritySettings(BaseSettings):
    ALLOWED_DOMAINS: str = ""
    ALLOWED_IPS: str = ""
    TWILIO_IP_RANGES: str = ""

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

    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ALLOWED_DOMAINS = self._parse_list_from_env(self.ALLOWED_DOMAINS)
        self.ALLOWED_IPS = self._parse_list_from_env(self.ALLOWED_IPS)
        self.TWILIO_IP_RANGES = self._parse_list_from_env(self.TWILIO_IP_RANGES)

    @staticmethod
    def _parse_list_from_env(value: str) -> List[str]:
        logger.debug(f"Raw value: {value}")
        if not value:
            logger.warning("Value is not set or is empty")
            return []
        parsed = [item.strip() for item in value.split(",") if item.strip()]
        logger.debug(f"Parsed value: {parsed}")
        return parsed

    def is_ip_allowed(self, ip: str) -> bool:
        if ip in self.ALLOWED_IPS:
            return True
        for ip_range in self.TWILIO_IP_RANGES:
            try:
                if ipaddress.ip_address(ip) in ipaddress.ip_network(ip_range, strict=False):
                    return True
            except ValueError:
                logger.error(f"Invalid IP range: {ip_range}")
        return False

try:
    security_settings = SecuritySettings()
    logger.debug(f"Allowed Domains: {security_settings.ALLOWED_DOMAINS}")
    logger.debug(f"Allowed IPs: {security_settings.ALLOWED_IPS}")
    logger.debug(f"Twilio IP Ranges: {security_settings.TWILIO_IP_RANGES}")
except Exception as e:
    logger.error(f"Error initializing security settings: {str(e)}")
    raise