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
from database.crud import seed_default_settings
from core.client import tg_manager
from core.broadcaster import broadcaster
from core.scheduler import scheduler

# Import Handlers
from handlers import (
    admin_menu,
    campaign_wizard,
    message_editor,
    group_manager,
    broadcast_ctrl,
    stats_report,
    account_auth,
    settings_menu
)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PromotionBot")

async def create_healthcheck_app():
    app = web.Application()
    async def health_handler(request):
        return web.Response(text="OK - Telegram Promotion Bot is Healthy", status=200)
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    return app

async def on_startup(bot: Bot):
    logger.info("Initializing Promotion Bot Database...")
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_default_settings(session)
    logger.info("Database & settings initialized successfully.")

    # Initialize Telethon Client (loads active sender account)
    logger.info("Starting Telegram Sender User Client...")
    await tg_manager.start()

    # Pass bot to broadcaster for admin alerts
    broadcaster.set_bot_instance(bot)

    # Start repeating scheduler
    logger.info("Starting Repeating Broadcast Scheduler...")
    scheduler.start()

async def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error("BOT_TOKEN is not configured in .env! Please set your Bot token.")
        return

    logger.info("Starting Telegram Promotion & Anti-Ban Bot...")

    session = AiohttpSession(timeout=30.0)
    bot = Bot(
        token=config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=MemoryStorage())

    # Register Handler Routers
    dp.include_router(admin_menu.router)
    dp.include_router(campaign_wizard.router)
    dp.include_router(message_editor.router)
    dp.include_router(group_manager.router)
    dp.include_router(broadcast_ctrl.router)
    dp.include_router(stats_report.router)
    dp.include_router(account_auth.router)
    dp.include_router(settings_menu.router)

    # Run startup initialization
    await on_startup(bot)

    # Delete webhook if any exists
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        logger.info(f"Webhook check: {e}")

    # Start Railway Web Healthcheck Server
    port = config.PORT
    health_app = await create_healthcheck_app()
    health_runner = web.AppRunner(health_app)
    await health_runner.setup()
    site = web.TCPSite(health_runner, "0.0.0.0", port)
    try:
        await site.start()
        logger.info(f"Healthcheck server listening on port {port}")
    except Exception as e:
        logger.warning(f"Could not bind web port {port}: {e}")

    logger.info(f"Bot connected as @{(await bot.get_me()).username}. Polling for updates...")

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
                logger.warning(f"Telegram network hiccup: {e}. Retrying in 2s...")
                await asyncio.sleep(2)
            except TelegramRetryAfter as e:
                logger.warning(f"Telegram rate limit: sleeping for {e.retry_after}s...")
                await asyncio.sleep(e.retry_after)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Bot shutdown requested.")
                break
            except Exception as e:
                logger.error(f"Polling loop error: {e}. Retrying in 3s...", exc_info=True)
                await asyncio.sleep(3)
    finally:
        scheduler.stop()
        await health_runner.cleanup()
        await bot.session.close()
        if tg_manager.client and tg_manager.client.is_connected():
            await tg_manager.client.disconnect()
        logger.info("Promotion Bot stopped cleanly.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Program exited.")
