import asyncio
import logging
from core.broadcaster import broadcaster
from database.database import AsyncSessionLocal
from database.crud import get_setting
import config

logger = logging.getLogger(__name__)

class PromotionScheduler:
    def __init__(self):
        self.is_running = False
        self.task: asyncio.Task | None = None

    async def _scheduler_loop(self):
        logger.info("Promotion Scheduler loop started.")
        while self.is_running:
            try:
                async with AsyncSessionLocal() as session:
                    is_enabled = await get_setting(session, "broadcast_enabled", "true")
                    interval_hours_str = await get_setting(session, "interval_hours", str(config.DEFAULT_INTERVAL_HOURS))
                    
                try:
                    interval_hours = float(interval_hours_str)
                except ValueError:
                    interval_hours = 2.0

                if is_enabled.lower() == "true":
                    logger.info(f"Triggering scheduled broadcast round (Interval: {interval_hours}h)...")
                    # Run the round asynchronously
                    asyncio.create_task(broadcaster.execute_broadcast_round(trigger_type="SCHEDULED"))
                else:
                    logger.info("Broadcast is paused in settings. Skipping this interval.")

                # Sleep for interval
                sleep_seconds = int(interval_hours * 3600)
                logger.info(f"Scheduler sleeping for {interval_hours} hours ({sleep_seconds}s) until next round...")
                
                # Check cancellation in smaller chunks
                for _ in range(sleep_seconds // 10):
                    if not self.is_running:
                        break
                    await asyncio.sleep(10)
                if self.is_running and (sleep_seconds % 10) > 0:
                    await asyncio.sleep(sleep_seconds % 10)

            except asyncio.CancelledError:
                logger.info("Scheduler task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self._scheduler_loop())
            logger.info("Promotion Scheduler started.")

    def stop(self):
        if self.is_running:
            self.is_running = False
            if self.task:
                self.task.cancel()
            logger.info("Promotion Scheduler stopped.")

scheduler = PromotionScheduler()
