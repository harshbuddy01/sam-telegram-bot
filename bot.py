import asyncio
import logging
import sys

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
from handlers import start, catalog, order, wallet, profile, admin

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

    # Run database initialization
    await on_startup()

    # Drop webhook once at startup
    try:
        await asyncio.wait_for(bot.delete_webhook(drop_pending_updates=False), timeout=5.0)
    except Exception as e:
        logger.info(f"Initial webhook check: {e}")

    logger.info(f"Bot connected as Admin IDs: {config.ADMIN_IDS}")
    logger.info("Polling for updates...")

    # Polling loop with automatic reconnection
    while True:
        try:
            await dp.start_polling(
                bot,
                polling_timeout=10,
                handle_signals=False
            )
            break
        except (TelegramServerError, TelegramNetworkError) as e:
            logger.warning(f"Telegram connection hiccup ({e}). Reconnecting in 2 seconds...")
            await asyncio.sleep(2)
        except TelegramRetryAfter as e:
            logger.warning(f"Telegram rate limit: sleeping for {e.retry_after} seconds...")
            await asyncio.sleep(e.retry_after)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot shutdown requested.")
            break
        except Exception as e:
            logger.error(f"Polling loop exception: {e}. Reconnecting in 3 seconds...")
            await asyncio.sleep(3)
    
    await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
