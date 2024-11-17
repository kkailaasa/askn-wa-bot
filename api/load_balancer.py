from fastapi import APIRouter, Request, Response, Depends, BackgroundTasks, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Dict, List, Optional, Tuple
import httpx
import time
import structlog
from db_scripts.load_balancer import LoadBalancerLog, NumberLoadStats
from db_scripts.base import SessionLocal
from core.config import settings
from services.auth import get_api_key
from utils.redis_helpers import redis_client
from datetime import datetime

router = APIRouter()
logger = structlog.get_logger(__name__)

class HybridLoadBalancer:
    def __init__(self):
        self.redis_client = redis_client
        self.current_index_key = "lb:current_index"

        # Load settings
        self.config = settings.load_balancer_config
        self.max_messages = settings.MAX_MESSAGES_PER_SECOND
        self.high_threshold = int(self.max_messages * settings.LOAD_BALANCER_HIGH_THRESHOLD)
        self.alert_threshold = int(self.max_messages * settings.LOAD_BALANCER_ALERT_THRESHOLD)
        self.stats_window = settings.LOAD_BALANCER_STATS_WINDOW

        # Use structlog's bind to create a logger with context
        self.logger = logger.bind(
            component="load_balancer",
            max_messages=self.max_messages,
            high_threshold=self.high_threshold,
            alert_threshold=self.alert_threshold,
            stats_window=self.stats_window
        )

        self.logger.info("load_balancer_initialized")

    def is_system_under_high_load(self, loads: Dict[str, float]) -> bool:
        """Check if system is under high load"""
        try:
            is_high = any(load > self.high_threshold for load in loads.values())
            self.logger.debug(
                "system_load_check",
                loads=loads,
                is_high_load=is_high
            )
            return is_high
        except Exception as e:
            self.logger.error(
                "system_load_check_failed",
                error=str(e),
                exc_info=True
            )
            return True  # Safely assume high load in case of error

    def get_number_load(self, number: str) -> float:
        """Get current load for a number"""
        try:
            key = f"msg_count:{number}"
            count = self.redis_client.get(key)
            load = float(count or 0)
            self.logger.debug(
                "number_load_check",
                number=number,
                load=load
            )
            return load
        except Exception as e:
            self.logger.error(
                "get_number_load_failed",
                number=number,
                error=str(e),
                exc_info=True
            )
            return 0.0

    def get_round_robin_number(self, numbers: List[str]) -> str:
        """Get next number using round-robin"""
        try:
            current_index = self.redis_client.incr(self.current_index_key) - 1
            if current_index >= len(numbers):
                self.redis_client.set(self.current_index_key, 0)
                current_index = 0
            selected = numbers[current_index]
            self.logger.debug(
                "round_robin_selection",
                selected_number=selected,
                current_index=current_index
            )
            return selected
        except Exception as e:
            self.logger.error(
                "round_robin_selection_failed",
                error=str(e),
                exc_info=True
            )
            fallback = numbers[int(time.time()) % len(numbers)]
            return fallback

    def get_least_loaded_number(self, loads: Dict[str, float]) -> str:
        """Get the least loaded number"""
        try:
            selected = min(loads.items(), key=lambda x: x[1])[0]
            self.logger.debug(
                "least_loaded_selection",
                selected_number=selected,
                loads=loads
            )
            return selected
        except Exception as e:
            self.logger.error(
                "least_loaded_selection_failed",
                error=str(e),
                exc_info=True
            )
            return list(loads.keys())[0]  # Return first number as fallback

    def select_number(self) -> Tuple[str, Dict[str, float]]:
        """Select the best number using hybrid approach"""
        try:
            numbers = settings.TWILIO_NUMBERS.split(',') if settings.TWILIO_NUMBERS else []
            if not numbers:
                raise ValueError("No WhatsApp numbers configured")

            # Get current loads
            loads = {num.strip(): self.get_number_load(num.strip()) for num in numbers}

            # Check system load status
            high_load = self.is_system_under_high_load(loads)

            if high_load:
                selected = self.get_least_loaded_number(loads)
                self.logger.info(
                    "load_balancer_decision",
                    decision_type="least_loaded",
                    selected_number=selected,
                    loads=loads
                )
            else:
                selected = self.get_round_robin_number(numbers)
                self.logger.info(
                    "load_balancer_decision",
                    decision_type="round_robin",
                    selected_number=selected,
                    loads=loads
                )

            return selected.strip(), loads

        except Exception as e:
            self.logger.error(
                "number_selection_failed",
                error=str(e),
                exc_info=True
            )
            # Fallback to first number
            fallback = numbers[0].strip() if numbers else ""
            return fallback, {}

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
                    messages_per_second=current_load,
                    timestamp=datetime.utcnow()
                )
                db.add(stats)
                db.commit()

                # Alert if load is very high
                if current_load >= settings.MAX_MESSAGES_PER_SECOND:
                    send_mattermost_alert(phone_number, current_load)
            finally:
                db.close()
    except Exception as e:
        logger.error(
            "increment_load_failed",
            phone_number=phone_number,
            error=str(e),
            exc_info=True
        )

async def send_mattermost_alert(phone_number: str, current_load: float):
    """Send alert to Mattermost when load exceeds threshold"""
    if not settings.MATTERMOST_WEBHOOK_URL:
        logger.warning("mattermost_webhook_not_configured")
        return

    try:
        message = {
            "text": f"⚠️ WARNING: WhatsApp number {phone_number} is experiencing high load "
                   f"({current_load:.2f} msgs/sec)"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.MATTERMOST_WEBHOOK_URL,
                json=message,
                timeout=5.0
            )
            
            if response.status_code != 200:
                logger.error(
                    "mattermost_alert_failed",
                    status_code=response.status_code,
                    response=response.text
                )
    except Exception as e:
        logger.error(
            "mattermost_alert_failed",
            error=str(e),
            exc_info=True
        )

@router.get("/signup")
async def signup(request: Request, background_tasks: BackgroundTasks):
    """Handle signup redirects to WhatsApp"""
    try:
        selected_number, current_loads = load_balancer.select_number()
        
        if not selected_number:
            raise HTTPException(
                status_code=503,
                detail="No WhatsApp numbers available"
            )

        background_tasks.add_task(increment_number_load, selected_number)

        # Log the redirect
        db = SessionLocal()
        try:
            log = LoadBalancerLog(
                client_ip=request.client.host,
                user_agent=request.headers.get("user-agent"),
                referrer=request.headers.get("referer"),
                assigned_number=selected_number,
                request_timestamp=datetime.utcnow(),
                additional_data={
                    "headers": dict(request.headers),
                    "query_params": dict(request.query_params),
                    "current_loads": current_loads
                }
            )
            db.add(log)
            db.commit()

            # Format WhatsApp URL
            wa_number = selected_number.replace("whatsapp:", "").replace("+", "").strip()
            redirect_url = f"https://wa.me/{wa_number}"

            logger.info(
                "signup_redirect",
                assigned_number=selected_number,
                client_ip=request.client.host,
                redirect_url=redirect_url
            )

            return RedirectResponse(url=redirect_url)

        except Exception as e:
            db.rollback()
            logger.error(
                "signup_db_error",
                error=str(e),
                exc_info=True
            )
            raise
        finally:
            db.close()

    except Exception as e:
        logger.error(
            "signup_failed",
            error=str(e),
            exc_info=True
        )
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
        numbers = settings.TWILIO_NUMBERS.split(',')
        stats = {
            number.strip(): load_balancer.get_number_load(number.strip())
            for number in numbers
        }

        logger.info(
            "load_stats_retrieved",
            stats=stats
        )

        return stats
    except Exception as e:
        logger.error(
            "load_stats_failed",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Error getting load statistics"
        )