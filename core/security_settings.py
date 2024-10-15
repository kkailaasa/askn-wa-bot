from typing import List
from pydantic_settings import BaseSettings
import ipaddress
import os

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
        return [item.strip() for item in value.split(",")] if value else []

    def is_ip_allowed(self, ip: str) -> bool:
        if ip in self.ALLOWED_IPS:
            return True
        for ip_range in self.TWILIO_IP_RANGES:
            try:
                if ipaddress.ip_address(ip) in ipaddress.ip_network(ip_range, strict=False):
                    return True
            except ValueError:
                print(f"Invalid IP range: {ip_range}")
        return False

security_settings = SecuritySettings()

# Print for debugging (remove in production)
print(f"Allowed Domains: {security_settings.ALLOWED_DOMAINS}")
print(f"Allowed IPs: {security_settings.ALLOWED_IPS}")
print(f"Twilio IP Ranges: {security_settings.TWILIO_IP_RANGES}")