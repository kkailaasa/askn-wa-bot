from typing import Optional, Tuple, Any
import time
import logging
from fastapi import Request

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, redis_client):
        self.redis_client = redis_client

    def get_identifier(self, request: Request, identifier_type: str) -> str:
        """Get the appropriate identifier based on the rate limit type"""
        if identifier_type == "ip_address":
            return request.client.host
        elif identifier_type == "phone_number":
            return request.path_params.get('phone_number') or request.query_params.get('phone_number')
        elif identifier_type == "email":
            return request.path_params.get('email') or request.query_params.get('email')
        else:
            raise ValueError(f"Unknown identifier type: {identifier_type}")

    async def is_rate_limited(
        self,
        request: Request,
        rate_limit_type: str,
        settings: Any
    ) -> Tuple[bool, Optional[int]]:
        """Check if the request is rate limited"""
        config = settings.rate_limit_config.get(rate_limit_type)
        if not config:
            logger.warning(f"No rate limit configuration found for {rate_limit_type}")
            return False, None

        identifier = self.get_identifier(request, config['identifier_type'])
        if not identifier:
            logger.warning(f"No identifier found for {rate_limit_type}")
            return False, None

        key = config['key_pattern'].format(**{config['identifier_type']: identifier})
        current_time = int(time.time())

        pipe = self.redis_client.pipeline()
        try:
            # Clean up old entries
            pipe.zremrangebyscore(key, 0, current_time - config['period'])
            # Count current entries
            pipe.zcard(key)
            # Add new entry
            pipe.zadd(key, {str(current_time): current_time})
            # Set expiry
            pipe.expire(key, config['period'])

            _, count, _, _ = pipe.execute()
            return count > config['limit'], config['period']

        except Exception as e:
            logger.error(f"Rate limit check failed: {str(e)}")
            return False, None

    async def get_remaining_limit(
        self,
        request: Request,
        rate_limit_type: str,
        settings: Any
    ) -> Tuple[int, int]:
        """Get remaining requests allowed and time until reset"""
        config = settings.rate_limit_config.get(rate_limit_type)
        if not config:
            return 0, 0

        identifier = self.get_identifier(request, config['identifier_type'])
        if not identifier:
            return 0, 0

        key = config['key_pattern'].format(**{config['identifier_type']: identifier})
        current_time = int(time.time())

        try:
            # Get current count
            count = await self.redis_client.zcount(
                key,
                current_time - config['period'],
                current_time
            )
            remaining = max(0, config['limit'] - count)

            # Get time until oldest request expires
            oldest = await self.redis_client.zrange(
                key,
                0,
                0,
                withscores=True
            )
            if oldest:
                ttl = int(oldest[0][1] + config['period'] - current_time)
            else:
                ttl = config['period']

            return remaining, max(0, ttl)

        except Exception as e:
            logger.error(f"Error getting rate limit info: {str(e)}")
            return 0, 0