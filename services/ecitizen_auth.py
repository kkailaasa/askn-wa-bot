from keycloak import KeycloakAdmin, KeycloakOpenIDConnection
from keycloak.exceptions import KeycloakError, KeycloakConnectionError, KeycloakAuthenticationError
from keycloak.urls_patterns import URL_TOKEN
from core.config import settings
from utils.redis_pool import get_redis_client
from services.rate_limiter import RateLimiter
from utils.redis_helpers import AsyncRedisLock, cache
from functools import lru_cache
import json
import logging
import secrets
import time
import redis
from typing import Dict, Any, Optional, List, Tuple
from fastapi import Request
import structlog
import aiohttp
import asyncio
from datetime import datetime, timedelta
import jwt
from core.sequence_errors import SequenceException, SequenceErrorCode

# Set up structured logging
logger = structlog.get_logger(__name__)

# Initialize Redis and rate limiter
redis_client = get_redis_client()
rate_limiter = RateLimiter(redis_client)

class KeycloakTokenManager:
    """Manages Keycloak token lifecycle"""
    def __init__(self):
        self.token_cache_key = "keycloak:admin:token"
        self.token_lock_key = "keycloak:token:lock"
        self.token = None
        self.token_expires_at = 0

    async def get_valid_token(self) -> str:
        """Get a valid token, refresh if needed"""
        current_time = time.time()

        # Check if current token is still valid (with 30s buffer)
        if self.token and self.token_expires_at > (current_time + 30):
            return self.token

        # Use distributed lock to prevent concurrent token refreshes
        async with AsyncRedisLock(self.token_lock_key, expire=30):
            # Check cache first
            cached_token = await cache.get(self.token_cache_key)
            if cached_token:
                token_data = json.loads(cached_token)
                if token_data['expires_at'] > (current_time + 30):
                    self.token = token_data['token']
                    self.token_expires_at = token_data['expires_at']
                    return self.token

            # Get new token
            try:
                async with aiohttp.ClientSession() as session:
                    token_url = f"{settings.KEYCLOAK_SERVER_URL}/realms/master/protocol/openid-connect/token"
                    async with session.post(
                        token_url,
                        data={
                            'grant_type': 'password',
                            'client_id': settings.KEYCLOAK_API_CLIENT_ID,
                            'username': settings.KEYCLOAK_USER_NAME,
                            'password': settings.KEYCLOAK_PASSWORD
                        }
                    ) as response:
                        if response.status != 200:
                            raise KeycloakAuthenticationError("Failed to get admin token")

                        token_data = await response.json()
                        self.token = token_data['access_token']
                        self.token_expires_at = current_time + token_data['expires_in']

                        # Cache the token
                        await cache.set(
                            self.token_cache_key,
                            json.dumps({
                                'token': self.token,
                                'expires_at': self.token_expires_at
                            }),
                            expiry=token_data['expires_in']
                        )

                        return self.token

            except Exception as e:
                logger.error(
                    "token_refresh_failed",
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise KeycloakAuthenticationError("Failed to refresh token")

class KeycloakHealthMonitor:
    """Monitors Keycloak server health"""
    def __init__(self):
        self.health_cache_key = "keycloak:health:status"
        self.last_check_key = "keycloak:health:lastcheck"
        self.check_interval = 60  # seconds

    async def get_health_status(self) -> Dict[str, Any]:
        """Get current health status with caching"""
        current_time = time.time()

        # Check cache first
        cached_status = await cache.get(self.health_cache_key)
        last_check = await cache.get(self.last_check_key)

        if cached_status and last_check and (current_time - float(last_check)) < self.check_interval:
            return json.loads(cached_status)

        # Perform health check
        try:
            async with aiohttp.ClientSession() as session:
                start_time = time.time()
                async with session.get(f"{settings.KEYCLOAK_SERVER_URL}/health") as response:
                    response_time = time.time() - start_time

                    health_status = {
                        'status': 'healthy' if response.status == 200 else 'unhealthy',
                        'response_time': response_time,
                        'timestamp': datetime.utcnow().isoformat(),
                        'details': await response.json() if response.status == 200 else None
                    }

                    # Cache the results
                    await cache.set(
                        self.health_cache_key,
                        json.dumps(health_status),
                        expiry=self.check_interval
                    )
                    await cache.set(
                        self.last_check_key,
                        str(current_time),
                        expiry=self.check_interval
                    )

                    return health_status

        except Exception as e:
            error_status = {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
            await cache.set(
                self.health_cache_key,
                json.dumps(error_status),
                expiry=30  # Shorter cache time for errors
            )
            return error_status

class ECitizenAuthService:
    """Enhanced Keycloak authentication service"""
    def __init__(self):
        self.token_manager = KeycloakTokenManager()
        self.health_monitor = KeycloakHealthMonitor()
        self.cache_prefix = "auth:"
        self._admin = None
        self._keycloak_connection = None

    async def get_admin(self) -> KeycloakAdmin:
        """Get Keycloak admin instance with valid token"""
        if not self._admin:
            token = await self.token_manager.get_valid_token()
            self._keycloak_connection = KeycloakOpenIDConnection(
                server_url=settings.KEYCLOAK_SERVER_URL,
                realm_name=settings.KEYCLOAK_REALM,
                user_realm_name="master",
                client_id=settings.KEYCLOAK_API_CLIENT_ID,
                verify=True
            )
            self._admin = KeycloakAdmin(connection=self._keycloak_connection)
            self._admin.token = token

        return self._admin

    async def health_check(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        return await self.health_monitor.get_health_status()

    async def get_user_by_email_or_username(
        self,
        request: Request,
        email: str
    ) -> Optional[Dict[str, Any]]:
        """Get user by email with enhanced error handling"""
        try:
            # Rate limit check
            is_limited = await rate_limiter.is_rate_limited(
                request=request,
                rate_limit_type="get_user_info",
                settings=settings
            )
            if is_limited:
                raise SequenceException(
                    error_code=SequenceErrorCode.RATE_LIMIT,
                    message="Rate limit exceeded for user lookups",
                    retry_after=60
                )

            # Check cache first
            cache_key = f"{self.cache_prefix}user:email:{email}"
            cached_user = await cache.get(cache_key)
            if cached_user:
                return json.loads(cached_user)

            admin = await self.get_admin()
            users = await asyncio.to_thread(admin.get_users, {"email": email})

            if not users:
                users = await asyncio.to_thread(admin.get_users, {"username": email})

            if users:
                user = users[0]
                user_data = {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "email": user.get("email"),
                    "enabled": user.get("enabled", False),
                    "attributes": user.get("attributes", {})
                }

                # Cache the result
                await cache.set(cache_key, json.dumps(user_data), expiry=300)
                return user_data

            return None

        except KeycloakError as e:
            logger.error(
                "keycloak_user_lookup_failed",
                email=email,
                error=str(e)
            )
            raise SequenceException(
                error_code=SequenceErrorCode.KEYCLOAK_ERROR,
                message="Failed to lookup user"
            )
        except Exception as e:
            logger.error(
                "user_lookup_failed",
                email=email,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def verify_email(self, request: Request, email: str) -> Dict[str, Any]:
        """Verify email with improved error handling"""
        try:
            # Rate limit check
            is_limited = await rate_limiter.is_rate_limited(
                request=request,
                rate_limit_type="verify_email",
                settings=settings
            )
            if is_limited:
                raise SequenceException(
                    error_code=SequenceErrorCode.RATE_LIMIT,
                    message="Too many email verification attempts",
                    retry_after=300
                )

            admin = await self.get_admin()
            users = await asyncio.to_thread(admin.get_users, {"email": email})

            if not users:
                raise SequenceException(
                    error_code=SequenceErrorCode.DATA_NOT_FOUND,
                    message="User not found"
                )

            user_id = users[0]['id']
            await asyncio.to_thread(
                admin.update_user,
                user_id=user_id,
                payload={"emailVerified": True}
            )

            logger.info("email_verified", email=email, user_id=user_id)
            return {"message": "Email verified successfully"}

        except KeycloakError as e:
            logger.error(
                "email_verification_failed",
                email=email,
                error=str(e)
            )
            raise SequenceException(
                error_code=SequenceErrorCode.KEYCLOAK_ERROR,
                message="Failed to verify email"
            )

    async def generate_otp(self) -> str:
        """Generate secure OTP"""
        return ''.join(secrets.choice('0123456789') for _ in range(6))

    async def store_otp(
        self,
        request: Request,
        email: str,
        otp: str,
        expiry: int = 600
    ) -> bool:
        """Store OTP with rate limiting"""
        try:
            # Rate limit check
            is_limited = await rate_limiter.is_rate_limited(
                request=request,
                rate_limit_type="send_otp",
                settings=settings
            )
            if is_limited:
                raise SequenceException(
                    error_code=SequenceErrorCode.RATE_LIMIT,
                    message="Too many OTP requests",
                    retry_after=300
                )

            otp_key = f"{self.cache_prefix}otp:{email}"
            attempts_key = f"{self.cache_prefix}otp:attempts:{email}"

            # Store OTP with attempts tracking
            async with AsyncRedisLock(f"otp_store:{email}"):
                await cache.set(otp_key, otp, expiry=expiry)
                await cache.set(attempts_key, "0", expiry=expiry)

            return True

        except Exception as e:
            logger.error(
                "otp_storage_failed",
                email=email,
                error=str(e)
            )
            raise

    async def verify_otp(
        self,
        request: Request,
        email: str,
        otp: str,
        max_attempts: int = 3
    ) -> Dict[str, bool]:
        """Verify OTP with attempt limiting"""
        try:
            # Rate limit check
            is_limited = await rate_limiter.is_rate_limited(
                request=request,
                rate_limit_type="verify_email",
                settings=settings
            )
            if is_limited:
                raise SequenceException(
                    error_code=SequenceErrorCode.RATE_LIMIT,
                    message="Too many verification attempts",
                    retry_after=300
                )

            otp_key = f"{self.cache_prefix}otp:{email}"
            attempts_key = f"{self.cache_prefix}otp:attempts:{email}"

            stored_otp = await cache.get(otp_key)
            if not stored_otp:
                return {"valid": False, "message": "OTP expired or not found"}

            async with AsyncRedisLock(f"otp_verify:{email}"):
                attempts = int(await cache.get(attempts_key) or 0)
                if attempts >= max_attempts:
                    return {
                        "valid": False,
                        "message": "Maximum verification attempts exceeded"
                    }

                if stored_otp == otp:
                    await cache.delete(otp_key)
                    await cache.delete(attempts_key)
                    return {"valid": True, "message": "OTP verified successfully"}

                # Increment attempts
                await cache.set(
                    attempts_key,
                    str(attempts + 1),
                    expiry=600
                )

                return {
                    "valid": False,
                    "message": f"Invalid OTP. {max_attempts - attempts - 1} attempts remaining"
                }

        except Exception as e:
            logger.error(
                "otp_verification_failed",
                email=email,
                error=str(e)
            )
            raise

# Export authentication service instance
auth_service = ECitizenAuthService()

# Expose methods as module-level functions
async def get_user_by_email_or_username(request, email):
    return await auth_service.get_user_by_email_or_username(request, email)

async def get_user_by_phone_or_username(request, phone):
    return await auth_service.get_user_by_phone_or_username(request, phone)

async def create_user_with_phone(request, **kwargs):
    return await auth_service.create_user_with_phone(request, **kwargs)

async def add_phone_attributes_to_user(user_id, attributes):
    return await auth_service.add_phone_attributes_to_user(user_id, attributes)

async def verify_email(request, email):
    return await auth_service.verify_email(request, email)

async def generate_otp():
    return await auth_service.generate_otp()

async def store_otp(request, email, otp):
    return await auth_service.store_otp(request, email, otp)

async def verify_otp(request, email, otp):
    return await auth_service.verify_otp(request, email, otp)

async def store_temp_data(key, data):
    return await auth_service.store_temp_data(key, data)

async def get_temp_data(key):
    return await auth_service.get_temp_data(key)

async def delete_temp_data(key):
    return await auth_service.delete_temp_data(key)

__all__ = [
    'auth_service',
    'get_user_by_email_or_username',
    'get_user_by_phone_or_username',
    'create_user_with_phone',
    'add_phone_attributes_to_user',
    'verify_email',
    'generate_otp',
    'store_otp',
    'verify_otp',
    'store_temp_data',
    'get_temp_data',
    'delete_temp_data'
]