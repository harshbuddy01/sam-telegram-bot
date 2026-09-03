import asyncio
import logging
import sys
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramServerError, TelegramNetworkError, TelegramRetryAfter

import config
from database.database import init_db, AsyncSessionLocal
from database.crud import seed_initial_data, purge_old_dummy_stocks
from middlewares.db import DatabaseSessionMiddleware
from handlers import start, catalog, order, wallet, profile, admin, support
from payments.webhook import create_webhook_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def on_startup():
    logger.info("Initializing database tables...")
    await init_db()
    
    logger.info("Syncing store catalog data...")
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
        await purge_old_dummy_stocks(session)
    
    logger.info("Database initialized and clean real inventory synced successfully.")

async def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error("BOT_TOKEN is not set in .env! Please configure your bot token first.")
        print("\n[ERROR] BOT_TOKEN is missing. Please edit .env and provide your Telegram Bot Token.\n")
        return

    logger.info("Starting Telegram Sales Bot...")

    # Initialize Bot instance with HTML Parse Mode & custom robust session
    session = AiohttpSession(timeout=30.0)
    bot = Bot(
        token=config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Initialize Dispatcher with Memory FSM storage
    dp = Dispatcher(storage=MemoryStorage())

    # Register Middlewares
    dp.update.middleware(DatabaseSessionMiddleware())

    # Register Handler Routers
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(order.router)
    dp.include_router(wallet.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    dp.include_router(support.router)

    # Run database initialization
    await on_startup()

    # Cache bot info at startup for reuse across handlers
    bot_me = await bot.get_me()
    bot._cached_me = bot_me
    logger.info(f"Bot connected as Admin IDs: {config.ADMIN_IDS}")

    # Drop webhook once at startup
    try:
        await asyncio.wait_for(bot.delete_webhook(drop_pending_updates=False), timeout=5.0)
    except Exception as e:
        logger.info(f"Initial webhook check: {e}")

    # Start Webhook HTTP Server (for Razorpay real-time callbacks & Railway healthchecks)
    port = int(os.getenv("PORT", 8080))
    webhook_app = create_webhook_app(bot, dp=dp)
    webhook_runner = web.AppRunner(webhook_app)
    await webhook_runner.setup()
    site = web.TCPSite(webhook_runner, "0.0.0.0", port)
    try:
        await site.start()
        logger.info(f"Webhook HTTP server started and listening on port {port}")
    except Exception as e:
        logger.warning(f"Could not bind webhook server on port {port}: {e}")

    # Start automated subscription expiry reminder background service
    from utils.expiry_notifier import start_expiry_reminder_scheduler
    asyncio.create_task(start_expiry_reminder_scheduler(bot))

    logger.info("Polling for updates...")

    # Polling loop with automatic reconnection
    try:
        while True:
            try:
                await dp.start_polling(
                    bot,
                    allowed_updates=dp.resolve_used_update_types(),
                    polling_timeout=30,
                    handle_signals=False,
                    close_bot_session=False
                )
                break
            except (TelegramServerError, TelegramNetworkError) as e:
                logger.warning(f"Telegram connection hiccup ({e}). Reconnecting in 1 second...")
                await asyncio.sleep(1)
            except TelegramRetryAfter as e:
                logger.warning(f"Telegram rate limit: sleeping for {e.retry_after} seconds...")
                await asyncio.sleep(e.retry_after)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Bot shutdown requested.")
                break
            except Exception as e:
                logger.error(f"Polling loop exception: {e}. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)
    finally:
        await webhook_runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
