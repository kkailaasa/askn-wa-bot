from fastapi import APIRouter, Request, Response, Depends
from fastapi.responses import RedirectResponse, JSONResponse
import redis
from typing import Dict, List, Optional, Tuple
import httpx
import time
import logging
from db_scripts.load_balancer import LoadBalancerLog, NumberLoadStats
from db_scripts.base import SessionLocal
from core.config import settings
from services.auth import get_api_key

router = APIRouter()
redis_client = redis.from_url(settings.REDIS_URL)
logger = logging.getLogger(__name__)

class HybridLoadBalancer:
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.current_index_key = "lb:current_index"
        # High load threshold (messages per second)
        self.high_load_threshold = settings.MAX_MESSAGES_PER_SECOND * 0.8  # 80% of max

    def get_number_load(self, number: str) -> float:
        """Get current load for a number"""
        try:
            key = f"msg_count:{number}"
            count = self.redis_client.get(key)
            return float(count or 0)
        except redis.RedisError as e:
            logger.error(f"Redis error getting load: {e}")
            return 0.0

    def is_system_under_high_load(self, loads: Dict[str, float]) -> bool:
        """Check if system is under high load"""
        return any(load > self.high_load_threshold for load in loads.values())

    def get_round_robin_number(self, numbers: List[str]) -> str:
        """Get next number using round-robin"""
        try:
            current_index = self.redis_client.incr(self.current_index_key) - 1
            if current_index >= len(numbers):
                self.redis_client.set(self.current_index_key, 0)
                current_index = 0
            return numbers[current_index]
        except redis.RedisError as e:
            logger.error(f"Redis error in round-robin: {e}")
            # Fallback to timestamp-based selection
            return numbers[int(time.time()) % len(numbers)]

    def get_least_loaded_number(self, loads: Dict[str, float]) -> str:
        """Get the least loaded number"""
        return min(loads.items(), key=lambda x: x[1])[0]

    def select_number(self) -> Tuple[str, Dict[str, float]]:
        """
        Select the best number using hybrid approach.
        Returns tuple of (selected_number, current_loads)
        """
        numbers = settings.TWILIO_NUMBERS
        if not numbers:
            raise ValueError("No WhatsApp numbers configured")

        try:
            # Get current loads
            loads = {num: self.get_number_load(num) for num in numbers}

            # Check system load status
            high_load = self.is_system_under_high_load(loads)

            if high_load:
                # Under high load, use least loaded number
                selected = self.get_least_loaded_number(loads)
                logger.info(f"High load detected, using least loaded number: {selected}")
            else:
                # Under normal load, use round-robin
                selected = self.get_round_robin_number(numbers)
                logger.info(f"Normal load, using round-robin number: {selected}")

            return selected, loads

        except Exception as e:
            logger.error(f"Error in number selection: {e}")
            # Fallback to simple round-robin
            fallback = numbers[int(time.time()) % len(numbers)]
            logger.info(f"Using fallback number: {fallback}")
            return fallback, {}

def select_number() -> str:
    """Main interface for number selection"""
    lb = HybridLoadBalancer(redis_client)
    selected, loads = lb.select_number()

    # Log selection for monitoring
    logger.info(f"Number selected: {selected}, Current loads: {loads}")

    return selected

def increment_number_load(phone_number: str):
    """Increment message count for a number"""
    timestamp = int(time.time())
    key = f"msg_count:{phone_number}"

    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 1)  # Expire after 1 second for per-second counting
    pipe.execute()

    current_load = float(redis_client.get(key) or 0)

    # Log to database if load is high
    if current_load >= settings.MAX_MESSAGES_PER_SECOND * 0.8:
        db = SessionLocal()
        try:
            stats = NumberLoadStats(
                phone_number=phone_number,
                messages_per_second=current_load
            )
            db.add(stats)
            db.commit()

            # Alert if load is very high
            if current_load >= settings.MAX_MESSAGES_PER_SECOND:
                send_mattermost_alert(phone_number, current_load)
        finally:
            db.close()

async def send_mattermost_alert(phone_number: str, current_load: float):
    """Send alert to Mattermost when load exceeds threshold"""
    message = {
        "text": f"⚠️ WARNING: WhatsApp number {phone_number} is experiencing high load "
                f"({current_load:.2f} msgs/sec)"
    }

    async with httpx.AsyncClient() as client:
        try:
            await client.post(settings.MATTERMOST_WEBHOOK_URL, json=message)
        except Exception as e:
            logger.error(f"Failed to send Mattermost alert: {str(e)}")

def get_number_load(phone_number: str) -> float:
    """Get current messages per second for a number"""
    key = f"msg_count:{phone_number}"
    current_count = redis_client.get(key)
    return float(current_count or 0)

@router.get("/signup")
async def signup(request: Request):
    """Handle signup redirects to WhatsApp"""
    selected_number = select_number()
    increment_number_load(selected_number)

    # Log the redirect
    db = SessionLocal()
    try:
        log = LoadBalancerLog(
            client_ip=request.client.host,
            user_agent=request.headers.get("user-agent"),
            referrer=request.headers.get("referer"),
            assigned_number=selected_number,
            additional_data={
                "headers": dict(request.headers),
                "query_params": dict(request.query_params)
            }
        )
        db.add(log)
        db.commit()
    finally:
        db.close()

    # Format WhatsApp URL
    wa_number = selected_number.replace("whatsapp:", "").replace("+", "")
    redirect_url = f"https://wa.me/{wa_number}"

    return RedirectResponse(url=redirect_url)

@router.get("/load-stats")
async def get_load_stats(request: Request, api_key: str = Depends(get_api_key)) -> Dict[str, float]:
    """Get current load statistics for all numbers"""
    return {
        number: get_number_load(number)
        for number in settings.TWILIO_NUMBERS
    }