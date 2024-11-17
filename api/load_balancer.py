from fastapi import APIRouter, Request, Response, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Dict, List, Optional, Tuple
import httpx
import time
import logging
from db_scripts.load_balancer import LoadBalancerLog, NumberLoadStats
from db_scripts.base import SessionLocal
from core.config import settings
from services.auth import get_api_key
from utils.redis_helpers import redis_client

router = APIRouter()
logger = logging.getLogger(__name__)

class HybridLoadBalancer:
    def __init__(self):
        self.redis_client = redis_client
        self.current_index_key = "lb:current_index"

        # Load settings with defaults
        self.max_messages = getattr(settings, 'MAX_MESSAGES_PER_SECOND', 70)
        self.high_threshold = getattr(settings, 'LOAD_BALANCER_HIGH_THRESHOLD', 0.8)
        self.alert_threshold = getattr(settings, 'LOAD_BALANCER_ALERT_THRESHOLD', 0.9)
        self.stats_window = getattr(settings, 'LOAD_BALANCER_STATS_WINDOW', 60)

        # Calculate thresholds
        self.high_load_threshold = self.max_messages * self.high_threshold
        self.alert_threshold = self.max_messages * self.alert_threshold

        logger.info(
            "Load balancer initialized",
            max_messages=self.max_messages,
            high_threshold=self.high_load_threshold,
            alert_threshold=self.alert_threshold
        )

    def get_number_load(self, number: str) -> float:
        """Get current load for a number"""
        try:
            key = f"msg_count:{number}"
            count = self.redis_client.get(key)
            return float(count or 0)
        except Exception as e:
            logger.error(f"Redis error getting load: {e}", exc_info=True)
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
        except Exception as e:
            logger.error(f"Redis error in round-robin: {e}", exc_info=True)
            return numbers[int(time.time()) % len(numbers)]

    def get_least_loaded_number(self, loads: Dict[str, float]) -> str:
        """Get the least loaded number"""
        return min(loads.items(), key=lambda x: x[1])[0]

    def select_number(self) -> Tuple[str, Dict[str, float]]:
        """Select the best number using hybrid approach"""
        numbers = settings.TWILIO_NUMBERS.split(',') if settings.TWILIO_NUMBERS else []
        if not numbers:
            raise ValueError("No WhatsApp numbers configured")

        try:
            # Get current loads
            loads = {num.strip(): self.get_number_load(num.strip()) for num in numbers}

            # Check system load status
            high_load = self.is_system_under_high_load(loads)

            if high_load:
                selected = self.get_least_loaded_number(loads)
                logger.info(f"High load detected, using least loaded number: {selected}")
            else:
                selected = self.get_round_robin_number(numbers)
                logger.info(f"Normal load, using round-robin number: {selected}")

            return selected, loads

        except Exception as e:
            logger.error(f"Error in number selection: {e}", exc_info=True)
            fallback = numbers[int(time.time()) % len(numbers)]
            logger.info(f"Using fallback number: {fallback}")
            return fallback.strip(), {}

# Initialize the load balancer
load_balancer = HybridLoadBalancer()

def increment_number_load(phone_number: str):
    """Increment message count for a number"""
    try:
        timestamp = int(time.time())
        key = f"msg_count:{phone_number}"

        pipe = load_balancer.redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 1)  # Expire after 1 second for per-second counting
        pipe.execute()

        current_load = float(load_balancer.redis_client.get(key) or 0)

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
    except Exception as e:
        logger.error(f"Error incrementing load: {e}", exc_info=True)

async def send_mattermost_alert(phone_number: str, current_load: float):
    """Send alert to Mattermost when load exceeds threshold"""
    if not settings.MATTERMOST_WEBHOOK_URL:
        logger.warning("Mattermost webhook URL not configured")
        return

    message = {
        "text": f"⚠️ WARNING: WhatsApp number {phone_number} is experiencing high load "
                f"({current_load:.2f} msgs/sec)"
    }

    try:
        async with httpx.AsyncClient() as client:
            await client.post(settings.MATTERMOST_WEBHOOK_URL, json=message)
    except Exception as e:
        logger.error(f"Failed to send Mattermost alert: {str(e)}", exc_info=True)

@router.get("/signup")
async def signup(request: Request, background_tasks: BackgroundTasks):
    """Handle signup redirects to WhatsApp"""
    try:
        selected_number, current_loads = load_balancer.select_number()
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
                    "query_params": dict(request.query_params),
                    "current_loads": current_loads
                }
            )
            db.add(log)
            db.commit()
        finally:
            db.close()

        # Format WhatsApp URL
        wa_number = selected_number.replace("whatsapp:", "").replace("+", "").strip()
        redirect_url = f"https://wa.me/{wa_number}"

        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"Error in signup endpoint: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )

@router.get("/load-stats")
async def get_load_stats(
    request: Request,
    api_key: str = Depends(get_api_key)
) -> Dict[str, float]:
    """Get current load statistics for all numbers"""
    try:
        numbers = settings.TWILIO_NUMBERS.split(',') if settings.TWILIO_NUMBERS else []
        return {
            number.strip(): load_balancer.get_number_load(number.strip())
            for number in numbers
        }
    except Exception as e:
        logger.error(f"Error getting load stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting load statistics")