import asyncio
import logging
from core.broadcaster import broadcaster
from database.database import AsyncSessionLocal
from database.crud import get_or_create_account_promo, get_all_sender_accounts, get_setting
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
                    accounts = await get_all_sender_accounts(session)

                if is_enabled.lower() != "true":
                    logger.info("Broadcast is paused globally. Skipping this interval.")
                    await self._sleep_interval(7200)
                    continue

                # Check each account's individual interval and enabled state
                for acc in accounts:
                    if acc.status != "ACTIVE":
                        continue

                    async with AsyncSessionLocal() as session:
                        promo = await get_or_create_account_promo(session, acc.id, acc.phone)

                    if not promo.is_enabled:
                        continue

                    interval_hours = promo.interval_hours or 2.0

                    # Check if enough time has passed since last run
                    import datetime
                    now = datetime.datetime.utcnow()
                    if promo.last_run_at:
                        elapsed = (now - promo.last_run_at).total_seconds()
                        if elapsed < (interval_hours * 3600):
                            continue

                    logger.info(f"Triggering scheduled broadcast for {acc.phone} (Interval: {interval_hours}h)...")
                    asyncio.create_task(
                        broadcaster.start_account_broadcast(acc.id, trigger_type="SCHEDULED")
                    )

                # Check every 60 seconds for due accounts
                await self._sleep_interval(60)

            except asyncio.CancelledError:
                logger.info("Scheduler task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _sleep_interval(self, seconds: int):
        """Sleep in small chunks so we can stop quickly."""
        for _ in range(seconds // 10):
            if not self.is_running:
                break
            await asyncio.sleep(10)
        if self.is_running and (seconds % 10) > 0:
            await asyncio.sleep(seconds % 10)

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
