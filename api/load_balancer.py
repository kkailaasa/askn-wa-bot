from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
import redis
from typing import Dict
import httpx
import time
import logging
from db_scripts.load_balancer import LoadBalancerLog, NumberLoadStats
from db_scripts.base import SessionLocal
from core.config import settings

router = APIRouter()
redis_client = redis.from_url(settings.REDIS_URL)
logger = logging.getLogger(__name__)

def get_number_load(phone_number: str) -> float:
    """Get current messages per second for a number"""
    key = f"msg_count:{phone_number}"
    current_count = redis_client.get(key)
    return float(current_count or 0)

def increment_number_load(phone_number: str):
    """Increment message count for a number"""
    timestamp = int(time.time())
    key = f"msg_count:{phone_number}"
    
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 1)  # Expire after 1 second for per-second counting
    pipe.execute()
    
    current_load = get_number_load(phone_number)
    
    # Log to database
    db = SessionLocal()
    try:
        stats = NumberLoadStats(
            phone_number=phone_number,
            messages_per_second=current_load
        )
        db.add(stats)
        db.commit()
        
        # Check for load threshold
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

def select_number() -> str:
    """Select the least loaded number"""
    loads = {num: get_number_load(num) for num in settings.TWILIO_NUMBERS}
    return min(loads.items(), key=lambda x: x[1])[0]

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
async def get_load_stats(request: Request) -> Dict[str, float]:
    """Get current load statistics for all numbers"""
    return {
        number: get_number_load(number)
        for number in settings.TWILIO_NUMBERS
    }