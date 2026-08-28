import asyncio
import logging
import datetime
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
                    logger.debug("Broadcast paused globally. Sleeping 2h.")
                    await self._sleep_interval(7200)
                    continue

                for acc in accounts:
                    if acc.status != "ACTIVE":
                        continue

                    # Always fetch a FRESH promo from DB — never use stale object
                    async with AsyncSessionLocal() as session:
                        promo = await get_or_create_account_promo(session, acc.id, acc.phone)

                        # Skip if this account's scheduler is turned OFF
                        if not promo.is_enabled:
                            continue

                        interval_hours = promo.interval_hours or 2.0
                        now = datetime.datetime.utcnow()

                        # If last_run_at is NULL, stamp it now and SKIP (wait full interval first)
                        if not promo.last_run_at:
                            promo.last_run_at = now
                            await session.commit()
                            logger.info(
                                f"Scheduler: Stamped {acc.phone} last_run_at=now. "
                                f"First auto-broadcast in {interval_hours}h."
                            )
                            continue

                        elapsed_seconds = (now - promo.last_run_at).total_seconds()
                        due_in = (interval_hours * 3600) - elapsed_seconds

                        if due_in > 0:
                            logger.debug(
                                f"Scheduler: {acc.phone} — next broadcast in "
                                f"{int(due_in // 60)}m {int(due_in % 60)}s"
                            )
                            continue

                    # Time has elapsed — fire the broadcast
                    logger.info(
                        f"Scheduler: Triggering broadcast for {acc.phone} "
                        f"(interval={interval_hours}h, elapsed={elapsed_seconds:.0f}s)"
                    )
                    asyncio.create_task(
                        broadcaster.start_account_broadcast(acc.id, trigger_type="SCHEDULED")
                    )

                # Poll every 60 seconds
                await self._sleep_interval(60)

            except asyncio.CancelledError:
                logger.info("Scheduler task cancelled.")
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _sleep_interval(self, seconds: int):
        """Sleep in 10-second chunks so we can stop quickly on shutdown."""
        slept = 0
        while self.is_running and slept < seconds:
            await asyncio.sleep(min(10, seconds - slept))
            slept += 10

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
