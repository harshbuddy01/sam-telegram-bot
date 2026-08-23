import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database.database import init_db, AsyncSessionLocal
from database.crud import seed_initial_data
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
    
    logger.info("Seeding initial store catalog data...")
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
    
    logger.info("Database initialized and catalog seeded successfully.")

async def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "your_telegram_bot_token_here":
        logger.error("BOT_TOKEN is not set in .env! Please configure your bot token first.")
        print("\n[ERROR] BOT_TOKEN is missing. Please edit .env and provide your Telegram Bot Token.\n")
        return

    logger.info("Starting Telegram Sales Bot...")

    # Initialize Bot instance with HTML Parse Mode
    bot = Bot(
        token=config.BOT_TOKEN,
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

    logger.info(f"Bot connected as Admin IDs: {config.ADMIN_IDS}")
    logger.info("Polling for updates...")

    try:
        # Drop pending updates to avoid processing backlog
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
