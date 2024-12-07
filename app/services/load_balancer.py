# app/services/load_balancer.py

import time
import aiohttp
import structlog
from typing import Dict, Optional
from app.core.config import settings
from app.utils.redis_helpers import message_counter, cache
from datetime import datetime

logger = structlog.get_logger()

class LoadBalancer:
    def __init__(self):
        """Initialize load balancer with configured Twilio numbers"""
        self.numbers = settings.TWILIO_NUMBERS
        if not self.numbers:
            raise ValueError("No Twilio numbers configured")

        # Load balancer thresholds
        self.high_threshold = settings.LOAD_BALANCER_HIGH_THRESHOLD
        self.alert_threshold = settings.LOAD_BALANCER_ALERT_THRESHOLD
        self.max_msgs_per_second = settings.MAX_MESSAGES_PER_SECOND
        self.stats_window = settings.LOAD_BALANCER_STATS_WINDOW

        # Cache keys
        self.last_alert_key = "load_balancer:last_alert:{}"
        self.number_status_key = "load_balancer:number_status:{}"

        logger.info(
            "load_balancer_initialized",
            number_count=len(self.numbers),
            high_threshold=self.high_threshold,
            alert_threshold=self.alert_threshold,
            max_msgs_per_second=self.max_msgs_per_second
        )

    async def send_mattermost_alert(self, number: str, load: float) -> None:
        """Send alert to Mattermost with rate limiting"""
        if not settings.MATTERMOST_WEBHOOK_URL:
            return

        # Check if we've sent an alert recently
        last_alert = await cache.get(self.last_alert_key.format(number))
        if last_alert:
            return  # Don't send alert if we've sent one recently

        message = {
            "text": (f"🚨 High Load Alert!\n"
                    f"WhatsApp number: {number}\n"
                    f"Current load: {load*100:.1f}%\n"
                    f"Time: {datetime.utcnow().isoformat()}")
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    settings.MATTERMOST_WEBHOOK_URL,
                    json=message,
                    timeout=5
                ) as response:
                    if response.status == 200:
                        # Set alert cooldown
                        await cache.set(
                            self.last_alert_key.format(number),
                            True,
                            expiry=300  # 5 minutes cooldown
                        )
                    else:
                        logger.error(
                            "mattermost_alert_failed",
                            status=response.status,
                            number=number,
                            load=load
                        )
            except Exception as e:
                logger.error(
                    "mattermost_alert_error",
                    error=str(e),
                    number=number
                )

    async def update_number_status(self, number: str, status: dict) -> None:
        """Update number status in cache"""
        await cache.set(
            self.number_status_key.format(number),
            status,
            expiry=self.stats_window
        )

    async def get_number_status(self, number: str) -> Optional[dict]:
        """Get number status from cache"""
        return await cache.get(self.number_status_key.format(number))

    async def get_available_number(self) -> Optional[str]:
        """Get the best available number based on current load"""
        min_load = float('inf')
        selected_number = None

        for number in self.numbers:
            try:
                # Get current message count
                current_count = await message_counter.get_count(number)
                current_load = current_count / self.max_msgs_per_second

                # Skip numbers above high threshold unless all numbers are high
                if current_load >= self.high_threshold and min_load < self.high_threshold:
                    continue

                # Send alert if load is too high
                if current_load >= self.alert_threshold:
                    await self.send_mattermost_alert(number, current_load)

                if current_load < min_load:
                    min_load = current_load
                    selected_number = number

                # Update status in cache
                await self.update_number_status(number, {
                    "load": current_load,
                    "message_count": current_count,
                    "last_updated": datetime.utcnow().isoformat()
                })

            except Exception as e:
                logger.error(
                    "load_check_error",
                    number=number,
                    error=str(e)
                )
                continue

        if selected_number:
            # Increment message count for selected number
            await message_counter.increment(selected_number)

            logger.info(
                "number_selected",
                number=selected_number,
                current_load=min_load*100
            )
        else:
            logger.error("no_available_numbers")

        return selected_number

    async def get_all_stats(self) -> Dict[str, Dict]:
        """Get current stats for all numbers"""
        stats = {}
        for number in self.numbers:
            try:
                # Get current message count
                count = await message_counter.get_count(number)
                load = count / self.max_msgs_per_second

                # Get cached status
                status = await self.get_number_status(number)

                stats[number] = {
                    "current_load_percentage": load * 100,
                    "message_count": count,
                    "status": status or "unknown",
                    "window_size": self.stats_window
                }
            except Exception as e:
                logger.error(
                    "stats_fetch_error",
                    number=number,
                    error=str(e)
                )
                stats[number] = {"error": str(e)}

        return stats

    async def health_check(self) -> Dict[str, Any]:
        """Check health of load balancer"""
        stats = await self.get_all_stats()
        total_load = sum(
            stat.get("current_load_percentage", 0) 
            for stat in stats.values()
        ) / len(self.numbers)

        return {
            "healthy": total_load < self.alert_threshold * 100,
            "total_load_percentage": total_load,
            "numbers_count": len(self.numbers),
            "stats": stats
        }