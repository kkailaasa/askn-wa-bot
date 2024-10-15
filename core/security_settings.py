from typing import List
from pydantic_settings import BaseSettings
import ipaddress
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class SecuritySettings(BaseSettings):
    ALLOWED_DOMAINS: List[str] = []
    ALLOWED_IPS: List[str] = []
    TWILIO_IP_RANGES: List[str] = []

    class Config:
        env_file = ".env"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ALLOWED_DOMAINS = self._parse_list_from_env("ALLOWED_DOMAINS")
        self.ALLOWED_IPS = self._parse_list_from_env("ALLOWED_IPS")
        self.TWILIO_IP_RANGES = self._parse_list_from_env("TWILIO_IP_RANGES")

    @staticmethod
    def _parse_list_from_env(key: str) -> List[str]:
        value = os.getenv(key, "")
        logger.debug(f"Raw value for {key}: {value}")
        parsed = [item.strip() for item in value.split(",")] if value else []
        logger.debug(f"Parsed value for {key}: {parsed}")
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

security_settings = SecuritySettings()

# Log for debugging (consider removing or changing to debug level in production)
logger.info(f"Allowed Domains: {security_settings.ALLOWED_DOMAINS}")
logger.info(f"Allowed IPs: {security_settings.ALLOWED_IPS}")
logger.info(f"Twilio IP Ranges: {security_settings.TWILIO_IP_RANGES}")